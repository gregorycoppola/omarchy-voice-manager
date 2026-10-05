import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intent_matching import IntentMatcher
from os_actions import tile_on_monitor
from runtime import VoiceRuntime

MONITORS = [{'id': 4, 'name': 'external', 'activeWorkspace': {'id': 7}},
            {'id': 0, 'name': 'internal', 'activeWorkspace': {'id': 3}}]


class MonitorTilingTests(unittest.TestCase):
    def test_phrases_have_structured_monitor_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for category, scope in [('terminals','terminals'), ('windows','open_windows'),
                                    ('browsers','browsers'), ('apps','apps')]:
                for phrase in (f'tile the {category} on monitor 2', f'tile {category} on screen two'):
                    result = matcher.parse(phrase)
                    self.assertEqual(result.command, f'{category}:tile-monitor:2')
                    self.assertEqual(result.canonical_plan[0]['arguments']['monitor'], '2')
                    self.assertEqual(result.canonical_plan[0]['arguments']['scope'], scope)

    def test_targets_requested_monitor_workspace_not_focused_context(self):
        clients = [{'address':'0x1','monitor':0,'workspace':{'id':3}},
                   {'address':'0x2','monitor':4,'workspace':{'id':7}}]
        with patch('os_actions.run', side_effect=[json.dumps(MONITORS), json.dumps(clients)]), \
             patch('os_actions.tile_open_windows', return_value='Tiled') as tile:
            message = VoiceRuntime.execute('terminals:tile-monitor:2',
                                           {'active':clients[0], 'clients':clients})
            tile.assert_called_once_with(
                {'active':{'monitor':4,'workspace':{'id':7}},'clients':clients},
                category='terminals')
            self.assertIn('Monitor 2 (external)', message)

    def test_missing_monitor_never_mutates_windows(self):
        with patch('os_actions.run', return_value=json.dumps(MONITORS)) as run, \
             patch('os_actions.tile_open_windows') as tile:
            with self.assertRaisesRegex(RuntimeError, 'not connected'):
                tile_on_monitor('terminals', 3)
            tile.assert_not_called()
            self.assertEqual(run.call_count,1)
