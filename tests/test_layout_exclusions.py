import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os_actions
from settings import Settings

CAMERA = {'address': '0xabc', 'class': 'example.overlay', 'initialClass': 'example.overlay',
          'pid': 12, 'mapped': True, 'workspace': {'id': 2}}


class LayoutExclusionTests(unittest.TestCase):
    def test_preferences_preserved_and_layout_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            settings = Settings(path / 'settings.json')
            settings.set_layout_excluded_classes(['example.overlay'])
            settings.set_confirm_terminal_close(False)
            restored = Settings(path / 'settings.json')
            self.assertEqual(restored.layout_excluded_classes, ['example.overlay'])
            self.assertFalse(restored.confirm_terminal_close)
            with patch('os_actions.DEFAULT_DATA', path), patch('os_actions.run') as run:
                context = {'active': CAMERA, 'clients': [CAMERA]}
                self.assertIn('No open', os_actions.tile_open_windows(context))
                self.assertEqual(os_actions.hide_window_targets([CAMERA], 2), (0, 0))
                for action in (os_actions.move_other_screen, os_actions.maximize_foreground,
                               os_actions.move_to_main_screen):
                    with self.assertRaisesRegex(RuntimeError, 'excluded'):
                        action(CAMERA)
                with self.assertRaisesRegex(RuntimeError, 'excluded'):
                    os_actions.tile_open_windows(context, selected_targets=[CAMERA])
                run.assert_not_called()
            with patch('os_actions.run', return_value=json.dumps([CAMERA])):
                self.assertEqual(os_actions.open_window_entries()[0]['address'], CAMERA['address'])

    def test_invalid_preferences_block_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            import personal_store
            personal_store.save(path/'settings.json', {
                'confirm_terminal_close': True, 'layout_excluded_classes': 'invalid'})
            with patch('os_actions.DEFAULT_DATA', path), patch('os_actions.run') as run:
                with self.assertRaisesRegex(RuntimeError, 'settings'):
                    os_actions.tile_open_windows({'active': CAMERA, 'clients': [CAMERA]})
                run.assert_not_called()

    def test_list_all_windows_phrase(self):
        self.assertEqual(os_actions.parse_command('list all windows'), 'windows:list')
        self.assertEqual(os_actions.parse_command('list all the windows'), 'windows:list')
