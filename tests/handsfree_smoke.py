"""Full hands-free GTK/VAD/ASR test with paced prerecorded audio, no microphone."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="keety-handsfree-test-") as directory:
    os.environ["XDG_DATA_HOME"] = directory
    import gui
    import listener
    from gi.repository import GLib

    original_popen = subprocess.Popen
    sample = str(Path(sys.argv[1]).resolve())
    producer = Path(directory) / "fake_mic.py"
    producer.write_text('''import sys,time,wave,signal
signal.signal(signal.SIGINT, lambda *args: sys.exit(1))
with wave.open(sys.argv[1]) as audio:
    pcm = b"\\0"*32000 + audio.readframes(audio.getnframes()) + b"\\0"*64000
for start in range(0,len(pcm),1024):
    sys.stdout.buffer.write(pcm[start:start+1024].ljust(1024,b"\\0"))
    sys.stdout.buffer.flush()
    time.sleep(.008)
while True:
    sys.stdout.buffer.write(b"\\0"*1024)
    sys.stdout.buffer.flush()
    time.sleep(.032)
''')

    def fake_mic(command, **kwargs):
        if command[0] == "pw-record":
            assert "--raw" in command
            command = [sys.executable, str(producer), sample]
        return original_popen(command, **kwargs)

    listener.subprocess.Popen = fake_mic
    app = gui.Keety()
    app.set_application_id("io.github.gregorycoppola.Keety.HandsfreeTest")
    start = time.monotonic()
    state = {"error": None}

    def step():
        try:
            assert time.monotonic() - start < 40, "Hands-free test timed out"
            if app.paths and not app.busy and app.listener:
                path = app.selected
                assert path.with_suffix(".txt").read_text().strip()
                assert path.with_suffix(".json").exists()
                assert app.recorder is None, "Manual recording must never be used"
                assert not app.record.get_sensitive()
                assert app.stop.get_sensitive()
                assert any(level > 0 for level in app.meter.levels)
                running = app.listener
                app.stop.emit("clicked")
                assert app.listener is None and not app.hands_free.get_active()
                assert app.record.get_sensitive()
                running.thread.join(timeout=3)
                assert not running.thread.is_alive(), "Pause must stop the capture thread"
                assert running.process.poll() is not None, "Pause must close the microphone stream"
                print("PASS: automatic listening, real VAD onset/end, real ASR, saved transcript, continued listening, Pause closes capture")
                app.quit()
                return False
        except Exception as exc:
            state["error"] = str(exc)
            if app.listener:
                app.listener.stop()
            app.quit()
            return False
        return True

    GLib.timeout_add(100, step)
    app.run(["keety-handsfree-test"])
    if state["error"]:
        raise SystemExit(state["error"])
