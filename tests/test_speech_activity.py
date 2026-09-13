import unittest

from speech_activity import SpeechSegmenter

SILENT = b"\0" * 1024
VOICE = b"\1\0" * 512


class SegmentTests(unittest.TestCase):
    def feed(self, gate, frames, score, pcm=SILENT):
        return [segment for _ in range(frames) if (segment := gate.feed(pcm, score)) is not None]

    def test_background_noise_never_starts_a_take(self):
        gate = SpeechSegmenter()
        self.assertEqual(self.feed(gate, 1000, .2), [])
        self.assertFalse(gate.active)

    def test_onset_preroll_and_silence_endpoint(self):
        gate = SpeechSegmenter()
        self.feed(gate, 15, .01)
        self.feed(gate, 10, .9, VOICE)
        self.assertTrue(gate.active)
        self.assertEqual(self.feed(gate, 21, .01), [])
        result = self.feed(gate, 1, .01)
        self.assertEqual(len(result), 1)
        self.assertIn(VOICE * 10, result[0])
        self.assertTrue(result[0].startswith(SILENT))
        self.assertFalse(gate.active)
        self.assertEqual(self.feed(gate, 100, .01), [])

    def test_short_click_like_burst_is_discarded(self):
        gate = SpeechSegmenter()
        self.feed(gate, 3, .9, VOICE)
        self.assertEqual(self.feed(gate, 22, .01), [])
        self.assertFalse(gate.active)

    def test_short_mid_sentence_pause_does_not_split(self):
        gate = SpeechSegmenter()
        self.feed(gate, 10, .9, VOICE)
        self.assertEqual(self.feed(gate, 10, .01), [])
        self.assertEqual(self.feed(gate, 10, .9, VOICE), [])
        self.assertEqual(len(self.feed(gate, 22, .01)), 1)

    def test_continuous_speech_remains_bounded(self):
        gate = SpeechSegmenter()
        results = self.feed(gate, 1900, .9, VOICE)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(len(pcm) <= 28 * 16000 * 2 for pcm in results))


if __name__ == "__main__":
    unittest.main()
