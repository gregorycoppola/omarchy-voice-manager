from pathlib import Path
import struct
import tempfile
import unittest

from live_audio import read_growing_wav


class GrowingWavTests(unittest.TestCase):
    def check_bytes(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recording.wav"
            path.write_bytes(data)
            return read_growing_wav(path)

    def header(self, length=0, rate=16000):
        fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
        return (b"RIFF" + struct.pack("<I", 0) + b"WAVE" + b"fmt " +
                struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", length))

    def test_unfinished_header_and_odd_sample(self):
        self.assertEqual(self.check_bytes(self.header() + b"\1\2\3\4\5"), b"\1\2\3\4")

    def test_partial_header_waits(self):
        self.assertIsNone(self.check_bytes(self.header()[:21]))

    def test_final_length_excludes_trailing_metadata(self):
        self.assertEqual(self.check_bytes(self.header(4) + b"\1\2\3\4LIST"), b"\1\2\3\4")

    def test_caps_unknown_length(self):
        self.assertEqual(len(self.check_bytes(self.header(0xFFFFFFFF) + b"\0" * 1000000)), 960000)

    def test_rejects_wrong_sample_rate(self):
        with self.assertRaises(ValueError):
            self.check_bytes(self.header(rate=48000) + b"\0\0")


if __name__ == "__main__":
    unittest.main()
