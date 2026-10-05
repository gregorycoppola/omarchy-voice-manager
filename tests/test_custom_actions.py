import personal_store
"""Named actions persist, stay exact, and reuse existing action routing."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from custom_actions import CustomActions
from intent_matching import IntentMatcher
from runtime import VoiceRuntime


class CustomActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'actions.json'
        self.store = CustomActions(self.path)
        self.matcher = IntentMatcher(self.root / 'aliases.json')

    def test_create_edit_remove_and_live_reload_without_learning(self):
        key = self.store.save('Quiet time', 'Make it quiet!', 'volume:mute')
        result = self.matcher.parse('make it quiet')
        self.assertEqual(result.command, 'volume:mute')
        self.assertEqual(result.selected.source, 'custom')
        self.assertEqual(result.selected.label, 'Quiet time')
        self.assertEqual(personal_store.database_path(self.path).stat().st_mode & 0o777, 0o600)
        self.store.save('Music time', 'soundtrack please', 'media:play', key)
        self.assertNotEqual(self.matcher.parse('make it quiet').command, 'volume:mute')
        self.assertEqual(self.matcher.parse('soundtrack please').command, 'media:play')
        self.store.remove(key)
        self.assertNotEqual(self.matcher.parse('soundtrack please').command, 'media:play')
        self.assertFalse(self.matcher.path.exists())

    def test_collisions_and_invalid_actions_leave_file_unchanged(self):
        self.store.save('Quiet', 'make it quiet', 'volume:mute')
        before = personal_store.load(self.path)
        for phrase, command in [('mute', 'volume:unmute'), ('make it quiet', 'media:play'),
                                ('do not make it quiet', 'volume:mute'), ('arbitrary', 'shell:run'),
                                ('tile foo and bar', 'media:play')]:
            with self.assertRaises(ValueError):
                self.store.save('Bad', phrase, command)
            self.assertEqual(personal_store.load(self.path), before)
        self.matcher.learn('launch the discord app', 'discord')
        with self.assertRaisesRegex(ValueError, 'learned'):
            self.store.save('Collision', 'launch the discord app', 'media:play')

    def test_custom_phrase_never_fuzzy_matches_or_learns(self):
        self.store.save('Quiet', 'make it quiet', 'volume:mute')
        for phrase in ('make it quiot', 'do not make it quiet'):
            self.assertNotEqual(self.matcher.parse(phrase).command, 'volume:mute')
        with self.assertRaisesRegex(ValueError, 'custom action'):
            self.matcher.learn('make it quiet', 'discord')

    def test_corrupt_file_fails_closed_and_cannot_be_overwritten(self):
        self.path.write_text('{bad json')
        store = CustomActions(self.path)
        self.assertTrue(store.error)
        self.assertIsNone(self.matcher.parse('make it quiet').command)
        with self.assertRaises(ValueError):
            store.save('Quiet', 'make it quiet', 'volume:mute')
        self.assertEqual(self.path.read_text(), '{bad json')

    def test_saved_semantics_cannot_silently_change(self):
        key = self.store.save('Quiet', 'make it quiet', 'volume:mute')
        data = personal_store.load(self.path)
        data['actions'][key]['command'] = 'volume:unmute'
        personal_store.save(self.path, data)
        self.assertIsNone(self.matcher.parse('make it quiet').command)

    def test_action_reaches_existing_terminal_confirmation(self):
        self.store.save('Done', 'finish this session', 'close:terminal_current')
        app = VoiceRuntime(self.root, self.root / 'status.json')
        target = {'address': '0x1', 'pid': 10, 'class': 'foot'}
        with patch('runtime.GLib.idle_add', side_effect=lambda fn, *a: fn(*a)), \
             patch('runtime.terminal_close_target', return_value=target), \
             patch('runtime.terminal_has_jobs', return_value=True), \
             patch.object(app, 'offer_confirmation') as confirm, patch.object(app, 'execute') as execute:
            app.interpret('finish this session', {}, source='written')
        confirm.assert_called_once_with('close:terminal_current', target, 'finish this session', False)
        execute.assert_not_called()
