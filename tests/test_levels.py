import struct
import unittest

from level_meter import pcm_level


class LevelTests(unittest.TestCase):
    def test_silence_does_not_fabricate_activity(self):
        self.assertEqual(pcm_level(b"\0\0" * 800), (0, -90))

    def test_amplitude_tracks_audio(self):
        quiet, quiet_db = pcm_level(struct.pack("<h", 1000) * 800)
        loud, loud_db = pcm_level(struct.pack("<h", 16000) * 800)
        self.assertGreater(loud, quiet)
        self.assertAlmostEqual(loud_db - quiet_db, 24.08, places=1)


if __name__ == "__main__":
    unittest.main()
