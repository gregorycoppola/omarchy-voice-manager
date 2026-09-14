"""Terminal tiling routing and window isolation, without moving real apps."""
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from command_catalog import STRUCTURED_INTENTS
from intent_matching import IntentMatcher
from os_actions import equal_grid, parse_command, tile_terminals, tile_browsers, tile_apps, tile_open_windows
from runtime import VoiceRuntime
from test_tile_windows import WINDOW, MONITOR

OTHER = dict(WINDOW, address='0x2', stableId='two', **{'class': 'chromium'})


class TileTerminalTests(unittest.TestCase):
    def test_phrases_and_runtime_context(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for phrase in ('tile all the terminals', 'tile all terminals', 'tile terminals',
                           'tile the terminals', 'tile open terminals', 'tile all open terminals'):
                self.assertEqual(parse_command(phrase), 'terminals:tile')
                self.assertEqual(matcher.parse(phrase).intent.type, 'tile_terminals')
            self.assertEqual(matcher.parse('tile all the termnals').command, 'terminals:tile')
        context = {'active': WINDOW, 'clients': [WINDOW, OTHER]}
        with patch('runtime.tile_terminals', return_value='Tiled') as action:
            self.assertEqual(VoiceRuntime.execute('terminals:tile', context), 'Tiled')
            action.assert_called_once_with(context)
        self.assertEqual(STRUCTURED_INTENTS['terminals:tile'].type, 'tile_terminals')

    def test_no_terminals_never_minimizes(self):
        with patch('os_actions.run') as run:
            self.assertIn('No open terminals', tile_terminals({'active': OTHER, 'clients': [OTHER]}))
            run.assert_not_called()
            with self.assertRaises(RuntimeError):
                tile_terminals(None)

    def scenario(self, other_live=OTHER, fail_move=False, visible=False):
        excluded = [dict(OTHER, address='0x3', workspace={'id': 3}),
                    dict(OTHER, address='0x4', mapped=False),
                    dict(OTHER, address='0x5', initialClass='io.github.gregorycoppola.Keety')]
        x, y, w, h = equal_grid(1, MONITOR)[0]
        final = dict(WINDOW, floating=True, fullscreen=0, fullscreenClient=0, at=[x,y], size=[w,h])
        clients = [dict(WINDOW), other_live, *excluded]
        dispatches = []
        def run(argv):
            if argv[1] == 'clients':
                return json.dumps(clients)
            if argv[1] == 'monitors':
                return json.dumps([dict(MONITOR, specialWorkspace={'name': 'special:keety-tile-2' if visible else ''})])
            dispatch = argv[-1]
            dispatches.append(dispatch)
            if 'relative = false, window = "address:0x1"' in dispatch and 'window.move' in dispatch:
                clients[0] = final
            if 'workspace = "special:keety-tile-2"' in dispatch and not fail_move:
                clients[1] = dict(other_live, workspace={'id': -99, 'name': 'special:keety-tile-2'})
            return 'ok'
        with patch('os_actions.run', side_effect=run):
            result = tile_terminals({'active': OTHER, 'clients': [WINDOW, OTHER, *excluded]})
        return result, dispatches

    def test_tiles_terminal_and_hides_only_other_workspace_apps(self):
        result, dispatches = self.scenario(visible=True)
        self.assertIn('Tiled 1 terminals', result)
        self.assertIn('Minimized 1 other windows', result)
        self.assertEqual(len(dispatches), 6)
        self.assertTrue(all('address:0x1' in d for d in dispatches[:4]))
        self.assertIn('address:0x2', dispatches[4])
        self.assertIn('follow = false', dispatches[4])
        self.assertIn('toggle_special', dispatches[5])

    def test_stale_nonterminal_not_minimized(self):
        for changed in (dict(OTHER, pid=101), dict(OTHER, stableId='replacement'),
                        dict(OTHER, workspace={'id': 3}), dict(OTHER, mapped=False)):
            result, dispatches = self.scenario(changed)
            self.assertIn('Skipped 1', result)
            self.assertIn('Minimized 0', result)
            self.assertEqual(len(dispatches), 4)

    def test_unconfirmed_minimization_is_error(self):
        with self.assertRaisesRegex(RuntimeError, 'could not confirm minimization'):
            self.scenario(fail_move=True)


class TileWorkflowTests(unittest.TestCase):
    def test_category_switches_restore_hidden_windows_and_all_restores_everything(self):
        clients = [dict(WINDOW), dict(OTHER),
                   dict(OTHER, address='0x3', stableId='three', **{'class': 'discord'}),
                   dict(OTHER, address='0x4', workspace={'id': 3}),
                   dict(OTHER, address='0x5', workspace={'id': -98, 'name': 'special:keety-tile-3'})]
        untouched = json.loads(json.dumps(clients[3:]))
        def run(argv):
            if argv[1] == 'clients':
                return json.dumps(clients)
            if argv[1] == 'monitors':
                return json.dumps([MONITOR])
            dispatch = argv[-1]
            address = re.search(r'address:(0x[0-9a-f]+)', dispatch).group(1)
            c = next(c for c in clients if c['address'] == address)
            if 'fullscreen_state' in dispatch:
                c.update(fullscreen=0, fullscreenClient=0)
            elif 'window.float' in dispatch:
                c['floating'] = True
            elif 'workspace =' in dispatch:
                destination = re.search(r'workspace = "([^"]+)"', dispatch).group(1)
                c['workspace'] = {'id': -99, 'name': destination} if destination.startswith('special:') else {'id': int(destination)}
            elif 'x =' in dispatch:
                x, y = map(int, re.search(r'x = (-?\d+), y = (-?\d+)', dispatch).groups())
                c['size' if 'resize' in dispatch else 'at'] = [x, y]
            return 'ok'
        with patch('os_actions.run', side_effect=run):
            for action, expected in [(tile_terminals, {'0x1'}), (tile_terminals, {'0x1'}),
                                     (tile_browsers, {'0x2'}), (tile_apps, {'0x2', '0x3'}),
                                     (tile_terminals, {'0x1'}), (tile_open_windows, {'0x1', '0x2', '0x3'})]:
                active = next(c for c in clients if c['workspace']['id'] == 2)
                context = json.loads(json.dumps({'active': active, 'clients': clients}))
                result = action(context)
                self.assertIn('Tiled', result)
                visible = [c for c in clients if c['workspace']['id'] == 2]
                self.assertEqual({c['address'] for c in visible}, expected)
                self.assertEqual({tuple(c['size']) for c in visible}, {equal_grid(len(expected), MONITOR)[0][2:]})
                self.assertEqual(clients[3:], untouched)

    def test_category_phrases_route(self):
        for category in ('browsers', 'apps'):
            command = category + ':tile'
            phrases = ('tile all apps',) if category == 'apps' else ('tile all browsers', 'tile all the browsers', 'tile browsers')
            for phrase in phrases:
                self.assertEqual(parse_command(phrase), command)
            context = {'active': WINDOW, 'clients': [WINDOW]}
            with patch('runtime.tile_' + category, return_value='Tiled') as action:
                VoiceRuntime.execute(command, context)
                action.assert_called_once_with(context)

    def test_apps_requires_literal_phrase_even_with_old_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'aliases.json'
            path.write_text(json.dumps({'version': 1, 'aliases': {
                'tile all that': 'apps:tile', 'tell the app': 'apps:tile',
                'pile all apps': 'apps:tile', 'pile all terminals': 'terminals:tile'}}))
            matcher = IntentMatcher(path)
            self.assertIsNone(matcher.error)
            self.assertEqual(matcher.parse('Tile all apps!').command, 'apps:tile')
            for phrase in ('tile all the apps', 'tile apps', 'tile the apps', 'tile all applications',
                           'tile applications', 'tile all that', 'tell the app', 'pile all apps',
                           'tile o apps', 'tile all terminals', 'tile all the terminals', 'tile l terminal'):
                self.assertNotEqual(matcher.exact(phrase), 'apps:tile', phrase)
                result = matcher.parse(phrase)
                self.assertNotEqual(result.command, 'apps:tile', phrase)
                self.assertFalse(any(c.command == 'apps:tile' for c in result.candidates), phrase)
            self.assertEqual(matcher.parse('tile all terminals').command, 'terminals:tile')
            self.assertEqual(matcher.parse('pile all terminals').command, 'terminals:tile')
            with self.assertRaisesRegex(ValueError, 'built-in phrase'):
                matcher.learn('tile all that', 'apps:tile')
