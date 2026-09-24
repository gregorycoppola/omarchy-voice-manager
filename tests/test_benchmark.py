import unittest

from benchmark import distance, normalize, score


class BenchmarkScoringTests(unittest.TestCase):
    def test_normalization_ignores_case_and_punctuation(self):
        self.assertEqual(normalize("Open Chrome!"), ["open", "chrome"])

    def test_distance_counts_word_substitutions(self):
        self.assertEqual(distance(["open", "chrome"], ["open", "chromium"]), 1)

    def test_score_reports_corpus_metrics(self):
        result = score("do not close chrome", "do close chrome")
        self.assertEqual(result["reference_words"], 4)
        self.assertEqual(result["word_edits"], 1)
        self.assertEqual(result["wer"], 0.25)
        self.assertFalse(result["exact"])


if __name__ == "__main__":
    unittest.main()
