"""Real GTK confirmation flow; fake transcription/actions, no microphone or OS actions."""
import os
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="keety-learning-test-") as directory:
    os.environ['XDG_DATA_HOME'] = directory
    import gui
    from gi.repository import GLib
    from intent_matching import IntentMatcher

    app = gui.Keety()
    installed = '--installed-id' in sys.argv
    if not installed:
        app.set_application_id('io.github.gregorycoppola.Keety.LearningTest')
    state = {'phase': 'load', 'error': None, 'passed': False}
    started = time.monotonic()
    path = gui.DATA / 'example.wav'

    def transcribe():
        app.set_busy(True)
        app.convert(path, commands=True)

    def step():
        try:
            assert time.monotonic() - started < 15, state
            phase = state['phase']
            if phase == 'load' and app.model and time.monotonic() - started > .5:
                transcribe()
                state['phase'] = 'reject'
            elif phase == 'reject' and app.pending_suggestion:
                if installed:
                    active = json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j']))
                    if active.get('title') != 'Keety — Confirm command':
                        return True
                    assert active['floating'] and active['size'] == [560, 280], active
                assert app.suggestion_dialog.get_visible()
                assert app.suggestion_dialog.get_modal()
                assert app.suggestion_dialog.get_transient_for() is app.window
                assert 'Open Discord' in app.suggestion_label.get_text()
                execute.assert_not_called()
                app.reject.emit('clicked')
                assert not app.suggestion_dialog.get_visible()
                assert not app.matcher.path.exists()
                transcribe()
                state['phase'] = 'escape'
            elif phase == 'escape' and app.pending_suggestion:
                assert app.suggestion_key(None, gui.Gdk.KEY_Escape, 0, 0)
                assert not app.suggestion_dialog.get_visible()
                execute.assert_not_called()
                transcribe()
                state['phase'] = 'close'
            elif phase == 'close' and app.pending_suggestion:
                app.suggestion_dialog.close()
                assert app.pending_suggestion is None
                execute.assert_not_called()
                transcribe()
                state['phase'] = 'stale'
            elif phase == 'stale' and app.pending_suggestion:
                app.select_recording()
                app.confirm.emit('clicked')
                execute.assert_not_called()
                assert not app.matcher.path.exists()
                transcribe()
                state['phase'] = 'accept'
            elif phase == 'accept' and app.pending_suggestion:
                app.confirm.emit('clicked')
                app.confirm.emit('clicked')  # double click cannot execute twice
                state['phase'] = 'learned'
            elif phase == 'learned' and not app.busy:
                execute.assert_called_once_with('discord')
                assert IntentMatcher(app.matcher.path).exact('open dis cord') == 'discord'
                assert not app.suggestion_dialog.get_visible()
                transcribe()
                state['phase'] = 'exact'
            elif phase == 'exact' and not app.busy:
                assert execute.call_count == 2
                assert app.pending_suggestion is None
                row = app.learned_list.get_first_child()
                row.get_last_child().emit('clicked')
                assert IntentMatcher(app.matcher.path).exact('open dis cord') is None
                print('PASS: GTK suggestion, No, stale dismissal, Yes once, persistent alias, exact reuse, Forget')
                state['passed'] = True
                app.window.close()
                # A hidden application-owned dialog must not keep Keety alive.
                def lingering():
                    state['passed'] = False
                    state['error'] = 'Closing the main window left the app running'
                    app.quit()
                    return False
                GLib.timeout_add(1000, lingering)
                return False
        except Exception as exc:
            state['error'] = repr(exc)
            app.quit()
            return False
        return True

    with patch('gui.load_model', return_value=(object(), 0)), \
         patch('gui.save_transcript', return_value=('open dis cord', {'audio_seconds': 1, 'transcribe_seconds': .1})), \
         patch('gui.execute_command', return_value='Opened Discord') as execute:
        GLib.timeout_add(50, step)
        app.run(['learning-smoke'])
    if not state['passed']:
        raise SystemExit(state['error'] or 'GUI test did not finish')
