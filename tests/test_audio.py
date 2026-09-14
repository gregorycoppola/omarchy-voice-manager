"""Input bounds must prevent unsupported/oversized clips reaching the model."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import wave

from skipper import transcribe


class AudioBoundsTests(unittest.TestCase):
    def test_rejects_unsupported_and_oversized_audio(self):
        for channels, rate, frames in [(2, 16000, 1600), (1, 48000, 4800),
                                      (1, 16000, 0), (1, 16000, 480001)]:
            with self.subTest(channels=channels, rate=rate, frames=frames):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "input.wav"
                    with wave.open(str(path), "wb") as audio:
                        audio.setnchannels(channels)
                        audio.setsampwidth(2)
                        audio.setframerate(rate)
                        audio.writeframes(b"\0\0" * channels * frames)
                    model = Mock()
                    with self.assertRaises(ValueError):
                        transcribe(model, path, 0)
                    model.recognize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
