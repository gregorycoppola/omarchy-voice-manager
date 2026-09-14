"""GApplication lifecycle and hold/release flow with synthetic audio, no microphone."""
import array
from pathlib import Path
import signal
import sys
import tempfile
import threading
import wave
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import VoiceRuntime
from gi.repository import GLib

class Recording:
    def __init__(self, argv, **kwargs):
        self.returncode = None
        self.stopped = threading.Event()
        with wave.open(argv[-1], 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(array.array('h', [6000, -6000] * 1600).tobytes())
    def poll(self):
        return self.returncode
    def communicate(self, timeout=None):
        assert self.stopped.wait(timeout)
        self.returncode = 1
        return '', ''
    def send_signal(self, value):
        assert value == signal.SIGINT
        self.stopped.set()
    def kill(self):
        self.stopped.set()

with tempfile.TemporaryDirectory() as directory:
    app = VoiceRuntime(directory, Path(directory) / 'status.json')
    app.set_application_id('io.github.gregorycoppola.Skipper.RuntimeTest')
    phase = ['loading']
    errors = []
    passed = []
    def step():
        try:
            if phase[0] == 'loading' and app.model:
                assert 'gi.repository.Gtk' not in sys.modules
                app.ptt.event('1-1:1:down')
                assert app.state['state'] == 'Recording'
                phase[0] = 'recording'
            elif phase[0] == 'recording':
                assert max(app.levels) > 0
                app.ptt.event('1-1:2:up')
                assert app.state['state'] == 'Working'
                phase[0] = 'working'
            elif phase[0] == 'working' and not app.busy:
                execute.assert_called_once_with('site:gmail', {}, None)
                assert app.state['intent']['arguments'] == {'destination': 'gmail'}
                assert app.state['completed_at'] > 0
                assert len(list((Path(directory) / 'recordings').glob('*.wav'))) == 1
                passed.append(True)
                app.request_quit()
                return False
        except Exception as exc:
            errors.append(repr(exc))
            app.quit()
            return False
        return True
    def timeout():
        errors.append('Timed out')
        app.quit()
        return False
    with patch('runtime.load_model', return_value=(object(), 0)), \
         patch('runtime.capture_window_context', return_value={}), \
         patch.object(app, 'focused_monitor', return_value='test'), \
         patch('runtime.subprocess.Popen', side_effect=Recording), \
         patch('runtime.save_transcript', return_value=('open gmail', {})), \
         patch.object(app, 'execute', return_value='Opened Gmail') as execute, \
         patch('runtime.connection.close'):
        GLib.timeout_add(200, step)
        GLib.timeout_add_seconds(10, timeout)
        app.run(['runtime-test'])
    assert passed and not errors, errors
    print('PASS: windowless startup, PTT press/release, actual PCM levels, structured dispatch, clean quit')
