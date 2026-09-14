"""Exercise tutorial navigation without loading speech or running voice commands."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer import Explorer
from gi.repository import GLib
from tutorial import LESSONS
from command_catalog import GRAMMAR

with tempfile.TemporaryDirectory() as directory:
    app = Explorer(Path(directory)/'aliases.json')
    app.set_application_id('io.github.gregorycoppola.Skipper.TutorialTest')
    errors = []
    def check():
        try:
            window = app.tutorial
            assert window and window.get_visible()
            assert app.window is None, 'Tutorial should not require the Explorer catalog window'
            app.show_tutorial()
            assert app.tutorial is window, 'Repeated launches should reuse the tutorial'
            assert not window.previous.get_sensitive()
            for index, lesson in enumerate(LESSONS):
                assert window.index == index
                for phrase, _ in lesson[3]:
                    assert phrase in GRAMMAR, phrase
                if index < len(LESSONS) - 1:
                    window.next.emit('clicked')
            assert window.next.get_label() == 'Done'
            window.previous.emit('clicked')
            assert window.index == len(LESSONS) - 2
            window.stack.set_visible_child_name('0')
            assert window.progress.get_text() == '1 of 6'
            assert 'skipper' not in sys.modules
            assert 'onnxruntime' not in sys.modules
            assert 'os_actions' not in sys.modules
            app.activate()
            catalog = app.window
            assert catalog and catalog.get_visible()
            catalog.close()
            assert app.window is None and app.windows_timer is None
            app.activate()
            assert app.window is not catalog
            app.hold()
            window.close()
            assert app.tutorial is None
            app.show_tutorial()
            assert app.tutorial is not window
            app.release()
            print('PASS: tutorial-only launch, six lessons, supported examples, navigation, reuse/reopen, no speech model or action imports')
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            app.quit()
        return False
    GLib.timeout_add(400, check)
    app.run(['tutorial-test', '--tutorial'])
    assert not errors, errors
