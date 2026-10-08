"""Written input shares the logical parser but bypasses speech and its corrections."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from corrections import Corrections
from runtime import VoiceRuntime


class WrittenTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        apps = self.root / 'installed'
        apps.mkdir()
        for name in ('Chrome', 'Discord'):
            (apps / (name.lower() + '.desktop')).write_text('[Desktop Entry]\nType=Application\nName=' + name + '\nExec=true\n')
        discovery = patch('installed_apps.application_dirs', return_value=(apps,))
        discovery.start()
        self.addCleanup(discovery.stop)
        self.app = VoiceRuntime(self.root, self.root / 'status.json')
        self.context = {'active': {'address': '0x1', 'monitor': 0, 'workspace': {'id': 1}}, 'clients': []}
        for context in [patch('runtime.GLib.idle_add', side_effect=lambda fn, *a: fn(*a)),
                        patch('runtime.capture_window_context', return_value=self.context),
                        patch.object(self.app, 'focused_monitor', return_value='eDP-1')]:
            context.start()
            self.addCleanup(context.stop)

    def submit(self, text):
        token = self.app.pending_written['token']
        with patch('runtime.threading.Thread') as worker:
            self.app.submit_written(json.dumps(dict(token=token, text=text)))
        worker.assert_called_once()
        kwargs = worker.call_args.kwargs
        kwargs['target'](*kwargs['args'])

    def test_unused_supported_commands_are_suggested_without_synthetic_history(self):
        self.app.type_command()
        entry = self.app.state['written_entry']
        self.assertNotIn('history', entry)
        self.assertEqual([row['command'] for row in entry['suggestions'] if row['text'].startswith('close ')], ['close:current_window'])
        self.assertFalse(any(row['text'].startswith('tile this window and') for row in entry['suggestions']))
        self.assertTrue(any(row['text'].startswith('open ') for row in entry['suggestions']))
        self.assertGreater(len(entry['suggestions']), 10)
        with self.app.command_store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 0)

    def test_installed_apps_appear_and_refresh_in_selector(self):
        apps = self.root / 'applications'
        apps.mkdir()
        with patch('installed_apps.application_dirs', return_value=(apps,)):
            self.app.type_command()
            entry = self.app.state['written_entry']
            self.assertFalse(any(row['command'].startswith('desktop-app:')
                                 for row in entry['dynamic_suggestions']))
            desktop = apps / 'tasks.desktop'
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Task Board\nExec=true\n')
            dynamic = self.app.command_suggestions(self.context)
            self.app.apply_written_refresh(entry['token'], self.context, dynamic)
            row = next(row for row in entry['dynamic_suggestions'] if row['text'] == 'open Task Board')
            self.assertIn('launch task board', row['forms'])
            self.assertNotIn('history', entry)
            self.app.cancel()
            self.app.type_command()
            self.assertIn(row, self.app.state['written_entry']['dynamic_suggestions'])
            desktop.unlink()
            dynamic = self.app.command_suggestions(self.context)
            self.app.apply_written_refresh(self.app.pending_written['token'], self.context, dynamic)
            self.assertFalse(any(row['command'].startswith('desktop-app:')
                                 for row in self.app.state['written_entry']['dynamic_suggestions']))

    def test_keyboard_mode_without_model_keeps_original_context(self):
        self.assertFalse(hasattr(self.app, 'model'))
        self.app.type_command()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.context['active']['monitor'] = 9
        self.assertEqual(self.app.pending_written['context']['active']['monitor'], 0)
        with patch('runtime.open_with_options', return_value='Opened') as execute:
            self.submit('open chrome')
        self.assertEqual(execute.call_args.args[0], 'desktop-app:chrome')
        self.assertEqual(execute.call_args.args[2]['active']['monitor'], 0)
        self.assertEqual(self.app.state['input_source'], 'written')
        self.assertEqual(self.app.state['written'], 'open chrome')
        self.assertIsNone(self.app.pending_written)

    def test_recognized_invocations_saved_but_not_suggested_on_reopen(self):
        for text in ['open chrome', 'open discord', 'open chrome']:
            self.app.type_command()
            with patch('runtime.open_with_options', return_value='Opened'):
                self.submit(text)
        self.app.type_command()
        entry = self.app.state['written_entry']
        self.assertNotIn('history', entry)
        self.assertEqual(entry['suggestions'], self.app.static_suggestions(self.context))
        self.assertEqual(entry['counts'], {'desktop-app:chrome': 2, 'desktop-app:discord': 1})
        with self.app.command_store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commands').fetchone()[0], 3)

    def test_written_bypasses_speech_corrections_and_does_not_train_speech_aliases(self):
        Corrections(self.root / 'corrections.json').save('open chrome', 'hide all apps', 'apps:hide')
        self.app.type_command()
        with patch('runtime.open_with_options', return_value='Opened') as execute:
            self.submit('open chrome')
        self.assertEqual(execute.call_args.args[0], 'desktop-app:chrome')
        self.app.type_command()
        with patch('runtime.open_with_options', return_value='Opened'):
            self.submit('open dis cord')
        self.assertFalse((self.root / 'aliases.json').exists())

    def test_unparsed_text_stays_in_dropdown_without_speech_question(self):
        self.app.type_command()
        with patch.object(self.app, 'offer_correction') as correction, patch.object(self.app, 'execute') as execute:
            self.submit('purple asparagus dances')
        correction.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.assertEqual(self.app.state['written_entry']['text'], 'purple asparagus dances')
        self.assertIsNotNone(self.app.pending_written)

    def test_shortcut_again_does_not_replace_pending_input(self):
        self.app.type_command()
        original = self.app.pending_written
        with patch.object(self.app, 'cancel') as cancel:
            self.app.type_command()
        self.assertIs(self.app.pending_written, original)
        cancel.assert_not_called()

    def test_cancel_rejects_old_submission(self):
        self.app.type_command()
        old = self.app.pending_written['token']
        self.app.cancel(old)
        self.app.type_command()
        with patch('runtime.threading.Thread') as worker:
            self.app.submit_written(json.dumps(dict(token=old, text='open chrome')))
        worker.assert_not_called()
        self.assertNotEqual(self.app.pending_written['token'], old)


if __name__ == '__main__':
    unittest.main()
