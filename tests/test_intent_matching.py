import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from command_catalog import GRAMMAR
from intent_matching import IntentMatcher


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "aliases.json"
        self.matcher = IntentMatcher(self.path)

    def test_builtin_vocabulary_unchanged(self):
        for phrase, intent in GRAMMAR.items():
            self.assertEqual(self.matcher.exact(phrase.upper() + "!"), intent)
            self.assertIsNone(self.matcher.suggest(phrase))

    def test_close_transcripts_suggest_intents_without_learning(self):
        for text, intent in [("show all the open windows", "windows"), ("open dis cord", "discord"), ("open chrom", "browser")]:
            self.assertEqual(self.matcher.suggest(text), intent)
            self.assertIsNone(self.matcher.exact(text))
        self.assertFalse(self.path.exists())

    def test_unrelated_negated_and_ambiguous_speech(self):
        for text in ["", "weather tomorrow", "do not open discord", "don't open chrome", "I was going to open Chrome.", "open"]:
            self.assertIsNone(self.matcher.suggest(text))
        with patch('intent_matching.GRAMMAR', {'open cat': 'discord', 'open bat': 'windows'}):
            self.assertIsNone(self.matcher.suggest('open hat'))

    def test_open_and_close_suggestions_have_distinct_intents(self):
        self.assertEqual(self.matcher.suggest("open dis cord"), "discord")
        self.assertEqual(self.matcher.suggest("close dis cord"), "close:discord")
        self.assertEqual(self.matcher.suggest("open twiter"), "x")
        self.assertEqual(self.matcher.suggest("close twiter"), "close:x")
        self.matcher.learn("close dis cord", "close:discord")
        self.assertEqual(IntentMatcher(self.path).exact("close dis cord"), "close:discord")
        self.assertEqual(self.matcher.exact("open discord"), "discord")

    def test_learning_reload_and_forgetting(self):
        self.matcher.learn(" Open DIS Cord! ", "discord")
        loaded = IntentMatcher(self.path)
        self.assertEqual(loaded.exact("open dis cord."), "discord")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        loaded.forget("open dis cord")
        self.assertIsNone(IntentMatcher(self.path).exact("open dis cord"))

    def test_conflicts_and_unknown_intents_rejected(self):
        for phrase, intent in [("open chrome", "discord"), ("something", "shell:rm"), ("", "discord")]:
            with self.assertRaises(ValueError):
                self.matcher.learn(phrase, intent)
        self.assertFalse(self.path.exists())

    def test_bad_file_is_not_overwritten(self):
        for contents in ['broken json', json.dumps({'version': 1, 'aliases': {'foo': 'unknown'}})]:
            self.path.write_text(contents)
            loaded = IntentMatcher(self.path)
            self.assertIsNotNone(loaded.error)
            self.assertEqual(loaded.exact('open chrome'), 'browser')
            with self.assertRaises(ValueError):
                loaded.learn('open dis cord', 'discord')
            self.assertEqual(self.path.read_text(), contents)

    def test_failed_save_does_not_learn_in_memory(self):
        with patch('intent_matching.os.fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.matcher.learn('open dis cord', 'discord')
        self.assertIsNone(self.matcher.exact('open dis cord'))
        self.assertEqual(list(self.path.parent.iterdir()), [])
