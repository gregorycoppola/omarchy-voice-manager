"""Named pair selection must retain two distinct captured window identities."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from picker_windows import pair_targets, parse, suggestions
from runtime import VoiceRuntime


def window(address, name, workspace=2):
    return dict(address=address, pid=int(address, 16), stableId=name + address,
                title=name, workspace={'id': workspace}, mapped=True, **{'class': 'foot'})


class NamedPairTests(unittest.TestCase):
    def setUp(self):
        self.clients = [window('0x1', 'Current'), window('0x2', 'Editor'), window('0x3', 'Docs', 4)]
        self.context = {'active': self.clients[0], 'clients': self.clients}

    def test_selects_two_named_windows_without_using_current(self):
        rows = pair_targets(self.context)
        self.assertEqual(len(rows), 3)
        first, second = rows[1:]
        phrase = f'tile {first[0]} and {second[0]}'
        result = parse(phrase, self.context)
        self.assertEqual(dict(result.intent.arguments), {'first': first[2], 'second': second[2]})
        plan = result.canonical_plan[0]
        self.assertEqual(plan['intent'], 'window.tile_pair')
        self.assertEqual(plan['arguments']['first'], {'kind': 'id', 'value': first[2]})
        with tempfile.TemporaryDirectory() as folder:
            app = VoiceRuntime(Path(folder), Path(folder) / 'status.json')
            with patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
                 patch('runtime.tile_selected_windows', return_value='Tiled two windows') as tile:
                app.interpret(phrase, self.context)
            tile.assert_called_once_with(self.context, [first[1], second[1]])
            self.assertEqual(app.state['state'], 'Ready')

    def test_duplicate_names_remain_distinct(self):
        self.context['clients'] = [window('0x1', 'Editor'), window('0x2', 'Editor')]
        rows = pair_targets(self.context)
        self.assertNotEqual(rows[0][0], rows[1][0])
        result = parse(f'tile {rows[0][0]} and {rows[1][0]}', self.context)
        self.assertEqual(result.intent.type, 'picker_tile_pair')
        self.assertIsNone(parse(f'tile {rows[0][0]} and {rows[0][0]}', self.context))

    def test_names_containing_and_do_not_split_incorrectly(self):
        self.context['clients'] = [window('0x1', 'Research and notes'), window('0x2', 'Docs')]
        rows = pair_targets(self.context)
        result = parse(f'tile {rows[0][0]} and {rows[1][0]}', self.context)
        self.assertEqual(result.intent.type, 'picker_tile_pair')

    def test_pair_provider_requires_two_distinct_windows(self):
        row = next(row for row in suggestions(self.context) if row.get('tileWindows'))
        self.assertEqual(len(row['tileWindows']), 3)
        self.context['clients'] = self.clients[:1]
        self.assertFalse(any(row.get('tileWindows') for row in suggestions(self.context)))

    def test_replacement_changes_execution_identity(self):
        rows = pair_targets(self.context)
        phrase = f'tile {rows[1][0]} and {rows[2][0]}'
        original = parse(phrase, self.context).command
        replacement = dict(self.clients[1], pid=777)
        changed = dict(self.context, clients=[self.clients[0], replacement, self.clients[2]])
        self.assertNotEqual(parse(phrase, changed).command, original)
        with tempfile.TemporaryDirectory() as folder:
            app = VoiceRuntime(Path(folder), Path(folder) / 'status.json')
            with patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)), \
                 patch('runtime.tile_selected_windows') as tile:
                app.interpret(phrase, changed, expected_command=original)
            tile.assert_not_called()
            self.assertEqual(app.state['state'], 'Error')
