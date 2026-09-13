"""Hidden startup, reopen/hide, PTT actions and bar status with no microphone."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as directory:
    os.environ.update(KEETY_BAR_MODE='1', XDG_DATA_HOME=directory, XDG_RUNTIME_DIR=directory)
    import gui
    from gi.repository import GLib
    app = gui.Keety()
    app.set_application_id('io.github.gregorycoppola.Keety.BarTest')
    result = []
    started = time.monotonic()
    def test():
        try:
            assert time.monotonic()-started<10
            if app.model is None:
                return True
            assert not app.window.get_visible()
            app.do_activate()
            assert app.window.get_visible()
            app.window.close()
            assert not app.window.get_visible()
            app.offer_terminal_close(Path(directory)/'test.wav', 'Saved', 'close terminal',
                                     'close:terminal', {'class':'foot','title':'Test job'}, False)
            assert app.suggestion_dialog.get_visible()
            assert not app.window.get_visible()
            app.dismiss_suggestion()
            recorder = Mock()
            recorder.poll.return_value = None
            def start():
                app.recorder = recorder
            with patch.object(app,'start_recording',side_effect=start) as record, patch.object(app,'stop_recording') as stop:
                app.activate_action('ptt-event',GLib.Variant('s','1-1:1:down'))
                record.assert_called_once()
                app.publish_bar_state()
                path = Path(directory)/f'keety-{os.getuid()}-status.json'
                assert json.loads(path.read_text())['state']=='Recording'
                app.window.close()
                stop.assert_not_called()
                app.activate_action('ptt-event',GLib.Variant('s','1-1:2:up'))
                stop.assert_called_once()
            app.recorder = None
            app.request_quit()
            assert json.loads(path.read_text())['state']=='Stopped'
            result.append('PASS: hidden startup, reopen/hide, background PTT down/up, recording status, explicit quit')
        except Exception as exc:
            result.append(exc)
            app.quit()
        return False
    with patch('gui.load_model',return_value=(object(),0)):
        GLib.timeout_add(100,test)
        app.run(['bar-test'])
    assert len(result)==1 and isinstance(result[0],str), result
    print(result[0])
