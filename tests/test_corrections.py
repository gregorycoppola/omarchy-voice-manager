import json
from pathlib import Path
import tempfile
import unittest

from command_history import recent_recordings
from corrections import Corrections
from intent_matching import IntentMatcher


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'corrections.json'
        self.matcher = IntentMatcher(self.root / 'aliases.json')

    def test_explicit_correction_precedes_grammar_and_reloads_without_restart(self):
        store = Corrections(self.path)
        store.save('Tile the terminals.', 'tile the apps', 'apps:tile', 'example.wav')
        result = self.matcher.parse('TILE THE TERMINALS!')
        self.assertEqual(result.command, 'apps:tile')
        self.assertEqual(result.method, 'correction')
        self.assertEqual(result.to_dict()['text'], 'TILE THE TERMINALS!')
        self.assertEqual(result.to_dict()['correction']['meant'], 'tile the apps')
        self.assertNotEqual(self.matcher.parse('tile terminals').method, 'correction')
        store.forget('tile the terminals')
        self.assertEqual(self.matcher.parse('tile the terminals').command, 'terminals:tile')
        self.assertEqual([e['action'] for e in Corrections(self.path).events], ['save', 'remove'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_explicit_choice_can_correct_exact_only_action_without_automatic_learning(self):
        Corrections(self.path).save('hide that stuff', 'hide all apps', 'apps:hide')
        self.assertEqual(self.matcher.parse('hide that stuff').command, 'apps:hide')
        self.assertIsNone(self.matcher.parse('hide other stuff').command)
        with self.assertRaises(ValueError):
            self.matcher.learn('hide other stuff', 'apps:hide')

    def test_invalid_file_is_not_overwritten_or_silently_ignored(self):
        self.path.write_text('{broken')
        result = self.matcher.parse('tile the terminals')
        self.assertIsNone(result.command)
        self.assertIn('Could not load corrections', result.reason)
        with self.assertRaises(ValueError):
            Corrections(self.path).save('x', 'tile the apps', 'apps:tile')
        self.assertEqual(self.path.read_text(), '{broken')

    def test_changes_retain_previous_rule_and_validate_action(self):
        store = Corrections(self.path)
        with self.assertRaises(ValueError):
            store.save('words', 'meaning', 'missing:action')
        store.save('words', 'tile all apps', 'apps:tile')
        store.save('words', 'tile all terminals', 'terminals:tile')
        self.assertEqual(store.events[-1]['previous']['command'], 'apps:tile')
        self.assertEqual(self.matcher.parse('words').command, 'terminals:tile')

    def test_history_keeps_original_transcript_and_parse_after_retry(self):
        directory = self.root / 'recordings'
        directory.mkdir()
        audio = directory / '2026-09-14_test.wav'
        audio.touch()
        audio.with_suffix('.txt').write_text('New transcription')
        log = self.root / 'commands.jsonl'
        events = [dict(event='transcript', commands_enabled=True, text='Original words'),
                  dict(event='parsed', command=None, result=dict(status='unrecognized', text='Original words')),
                  dict(event='state', state='Ready', message='Unrecognized command'),
                  dict(event='transcript', commands_enabled=False, text='New transcription'),
                  dict(event='parsed', command=None, result=None),
                  dict(event='state', state='Ready', message='Transcript updated')]
        log.write_text('\n'.join(json.dumps(e | dict(recording=str(audio))) for e in events) + '\n{partial')
        record = recent_recordings(directory, log)[0]
        self.assertEqual(record['heard'], 'Original words')
        self.assertEqual(record['parsed']['status'], 'unrecognized')
        self.assertEqual(record['outcome'], 'Unrecognized command')
