"""Exercise GTK Record/Stop/save/history with real ASR and a fake microphone.

Run from the repo: .venv/bin/python tests/gui_smoke.py local/jfk.wav
No real microphone access. All test recordings live in a temporary directory.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="keety-gui-test-") as directory:
    os.environ["XDG_DATA_HOME"] = directory
    import gui
    from gi.repository import GLib

    original_popen = subprocess.Popen
    sample = Path(sys.argv[1]).resolve()
    automatic = "--auto" in sys.argv

    def fake_microphone(command, **kwargs):
        if command[0] == "pw-record":
            command = [sys.executable, "-c",
                       "import shutil,sys,time,signal; signal.signal(signal.SIGINT, lambda *args: sys.exit(1)); shutil.copyfile(sys.argv[1],sys.argv[2]); time.sleep(float(sys.argv[3]))",
                       str(sample), command[-1], "1" if automatic else "30"]
        return original_popen(command, **kwargs)

    gui.subprocess.Popen = fake_microphone
    app = gui.Keety(hands_free_default=False)
    app.set_application_id("io.github.gregorycoppola.Keety.Test")
    started = time.monotonic()
    state = {"phase": "load", "error": None}

    def step():
        try:
            assert time.monotonic() - started < 45, "GUI test timed out"
            if state["phase"] == "load" and app.model and app.record.get_sensitive():
                app.record.emit("clicked")
                assert app.busy and app.stop.get_sensitive()
                state.update(phase="record", since=time.monotonic())
            elif state["phase"] == "record":
                buffer = app.text.get_buffer()
                text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
                assert "country" not in text, "No live text preview during recording"
                if not any(level > 0 for level in app.meter.levels):
                    return True
                assert app.recorder.poll() is None, "Meter must respond during recording"
                if not automatic:
                    app.stop.emit("clicked")
                state["phase"] = "save"
            elif state["phase"] == "save" and not app.busy:
                wav = app.selected
                assert wav and wav.is_file()
                assert "country" in wav.with_suffix(".txt").read_text()
                assert wav.with_suffix(".json").is_file()
                buffer = app.text.get_buffer()
                assert "country" in buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False), "Stop must display transcript without retry"
                assert app.record.get_sensitive() and not app.stop.get_sensitive()
                app.refresh_history()  # reload from disk, not transient widget state
                assert app.selected == wav
                assert app.copy.get_sensitive() and app.play.get_sensitive()
                print("PASS:", "automatic recording end" if automatic else "Stop exit-code-1 regression",
                      "— actual amplitude meter, no live text, automatic visible transcript, saved WAV/text/metrics, disk history")
                app.quit()
                return False
        except Exception as exc:
            state["error"] = str(exc)
            if app.recorder and app.recorder.poll() is None:
                app.recorder.kill()
                app.recorder.wait()
            app.quit()
            return False
        return True

    GLib.timeout_add(100, step)
    app.run(["keety-gui-test"])
    if state["error"]:
        raise SystemExit(state["error"])
