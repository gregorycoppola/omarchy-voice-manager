import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intent_matching import IntentMatcher
from os_actions import tile_in_workspace


class TileWorkspaceTests(unittest.TestCase):
    def test_exact_scopes_and_invalid_destinations(self):
        with tempfile.TemporaryDirectory() as folder:
            matcher = IntentMatcher(Path(folder) / 'aliases.json')
            for category in ('windows', 'terminals', 'browsers'):
                for quantifier in ('all', 'open'):
                    for destination, suffix in [('this workspace', 'current'), ('workspace 2', '2')]:
                        result = matcher.parse(f'tile {quantifier} {category} in {destination}')
                        self.assertEqual(result.command, f'{category}:tile-workspace:{suffix}')
                        self.assertEqual(result.canonical_plan[0]['arguments'].get('workspace'), 2 if suffix == '2' else None)
            for destination in ('workspace 0', 'workspace -2', 'workspace nope'):
                self.assertEqual(matcher.parse('tile all windows in ' + destination).status, 'unrecognized')

    def test_uses_destination_monitor_and_preserves_capture(self):
        context = {'active': {'monitor': 1, 'workspace': {'id': 1}}, 'clients': [{'address': '0x1'}]}
        with patch('os_actions.run', side_effect=[json.dumps([{'id': 2, 'monitor': 'external'}]),
                json.dumps([{'id': 3, 'name': 'external'}])]), patch('os_actions.tile_open_windows', return_value='Tiled') as tile:
            tile_in_workspace(context, 'terminals', '2')
            tile.assert_called_once_with({'active': {'monitor': 3, 'workspace': {'id': 2}},
                                          'clients': context['clients']}, category='terminals')
        self.assertEqual(context['active']['workspace']['id'], 1)

    def test_missing_workspace_does_not_tile_current(self):
        with patch('os_actions.run', return_value='[]'), patch('os_actions.tile_open_windows') as tile:
            self.assertIn('No open', tile_in_workspace({}, 'windows', '3'))
            tile.assert_not_called()

    def test_default_retains_captured_workspace(self):
        context = {'active': {'workspace': {'id': 4}}}
        with patch('os_actions.tile_open_windows', return_value='Tiled') as tile:
            tile_in_workspace(context, 'browsers', 'current')
            tile.assert_called_once_with(context, category='browsers')
