"""Exercise terminal close confirmation/settings in GTK, without closing real terminals."""
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix='skipper-terminal-test-') as directory:
    os.environ['XDG_DATA_HOME'] = directory
    import gui
    from gi.repository import GLib
    from settings import Settings
    app = gui.Skipper()
    app.set_application_id('io.github.gregorycoppola.Skipper.TerminalTest')
    target = {'class':'foot', 'address':'0x1', 'pid':100, 'title':'My editor'}
    context = {'active':target, 'clients':[target]}
    text = ['close this terminal']
    jobs = [True]
    state = {'phase':'load', 'passed':False, 'error':None}
    started = time.monotonic()

    def convert():
        app.set_busy(True)
        app.convert(gui.DATA/'test.wav', commands=True, context=context)

    def step():
        try:
            assert time.monotonic()-started < 15, state
            phase = state['phase']
            if phase == 'load' and app.model:
                convert()
                state['phase'] = 'no'
            elif phase == 'no' and app.pending_suggestion:
                assert app.suggestion_label.get_text() == 'My editor'
                close.assert_not_called()
                app.reject.emit('clicked')
                close.assert_not_called()
                convert()
                state['phase'] = 'yes'
            elif phase == 'yes' and app.pending_suggestion:
                # Focus changes after the prompt must not change the chosen terminal.
                context['active'] = {'class':'foot', 'address':'0x2', 'pid':200}
                app.confirm.emit('clicked')
                app.confirm.emit('clicked')
                state['phase'] = 'closed'
            elif phase == 'closed' and not app.busy:
                close.assert_called_once_with(target)
                assert not app.matcher.path.exists(), 'Exact confirmation must not learn an alias'
                app.confirm_terminal.set_active(False)
                assert not Settings(app.settings.path).confirm_terminal_close
                context['active'] = target
                convert()
                state['phase'] = 'disabled'
            elif phase == 'disabled' and not app.busy:
                assert close.call_count == 2
                assert app.pending_suggestion is None
                app.confirm_terminal.set_active(True)
                jobs[0] = False
                convert()
                state['phase'] = 'idle'
            elif phase == 'idle' and not app.busy:
                assert close.call_count == 3, 'Idle shell should close without asking'
                assert app.pending_suggestion is None
                jobs[0] = None
                convert()
                state['phase'] = 'unknown'
            elif phase == 'unknown' and app.pending_suggestion:
                assert close.call_count == 3
                app.reject.emit('clicked')
                app.confirm_terminal.set_active(False)
                text[0] = 'close this termnal'
                convert()
                state['phase'] = 'fuzzy'
            elif phase == 'fuzzy' and not app.busy:
                assert app.pending_suggestion is None
                assert close.call_count == 4
                assert app.matcher.exact('close this termnal') == 'close:terminal_current'
                state['passed'] = True
                print('PASS: terminal title confirmation, cancel, fixed target, one close, saved opt-out, automatic fuzzy learning')
                app.window.close()
                return False
        except Exception as exc:
            state['error'] = repr(exc)
            app.quit()
            return False
        return True

    with patch('gui.load_model', return_value=(object(),0)), \
         patch('gui.save_transcript', side_effect=lambda *_: (text[0], {'audio_seconds':1, 'transcribe_seconds':.1})), \
         patch('gui.terminal_has_jobs', side_effect=lambda _: jobs[0]), \
         patch('gui.close_terminal', return_value='Asked terminal to close') as close:
        GLib.timeout_add(50, step)
        app.run(['terminal-confirmation-test'])
    if not state['passed']:
        raise SystemExit(state['error'] or 'Test did not finish')
