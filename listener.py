"""Continuous PipeWire capture; only speech segments leave the in-memory buffer."""
import signal
import subprocess
import tempfile
import threading

from speech_activity import SpeechDetector, SpeechSegmenter, FRAME_SAMPLES


class Listener:
    def __init__(self, on_level, on_state, on_segment, on_error):
        self.on_level = on_level
        self.on_state = on_state
        self.on_segment = on_segment
        self.on_error = on_error
        self.stopped = threading.Event()
        self.process = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.capture, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass

    def capture(self):
        try:
            detector = SpeechDetector()
            segmenter = SpeechSegmenter()
            if self.stopped.is_set():
                return
            with tempfile.TemporaryFile() as errors:
                self.process = subprocess.Popen([
                    "pw-record", "--raw", "--rate", "16000", "--channels", "1",
                    "--format", "s16", "-",
                ], stdout=subprocess.PIPE, stderr=errors)
                if self.stopped.is_set():
                    self.stop()
                    return
                self.on_state(False)
                count = 0
                while not self.stopped.is_set():
                    pcm = self.process.stdout.read(FRAME_SAMPLES * 2)
                    if len(pcm) != FRAME_SAMPLES * 2:
                        if not self.stopped.is_set():
                            raise RuntimeError("Microphone stream ended unexpectedly")
                        break
                    score = detector.probability(pcm)
                    before = segmenter.active
                    segment = segmenter.feed(pcm, score)
                    count += 1
                    if count % 2 == 0:
                        self.on_level(pcm, score)
                    if before != segmenter.active:
                        self.on_state(segmenter.active)
                    if segment is not None and not self.stopped.is_set():
                        self.on_segment(segment)
        except Exception as exc:
            if not self.stopped.is_set():
                self.on_error(str(exc))
        finally:
            self.stop()
            if self.process:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                if self.process.stdout:
                    self.process.stdout.close()
