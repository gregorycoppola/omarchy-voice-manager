"""Pair parsing, slot questions, runtime picker identity, and stale targets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from window_resolution import WindowResolution
from runtime import VoiceRuntime
from os_actions import tile_selected_windows

TERM = dict(address='0x1', pid=1, stableId='one', title='Project',
            workspace={'id': 1}, monitor=0, mapped=True, **{'class': 'foot'})
BROWSER = dict(TERM, address='0x2', pid=2, stableId='two', title='Docs', **{'class': 'chromium'})
OTHER = dict(BROWSER, address='0x3', pid=3, stableId='three', title='Mail')


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.matcher = IntentMatcher(self.data / 'aliases.json')

    def resolution(self, phrase='tile this window and the browser', clients=None):
        result = self.matcher.parse(phrase)
        self.assertIn(result.intent.type, ('tile_pair', 'tile_current_window_with_browser'))
        return WindowResolution(result.intent, {'active': TERM, 'clients': clients or [TERM, BROWSER]})

    def test_unique_references_need_no_question_and_capture_is_frozen(self):
        r = self.resolution()
        self.assertIsNone(r.advance())
        self.assertEqual(r.resolved, {'first': TERM, 'second': BROWSER})
        self.assertIsNot(r.resolved['first'], TERM)

    def test_ambiguous_second_and_first_slots(self):
        for phrase, slot in [('tile this window and the browser', 'second'),
                             ('tile the browser and this window', 'first')]:
            r = self.resolution(phrase, [TERM, BROWSER, OTHER])
            q = r.advance()
            self.assertEqual(q.slot, slot)
            self.assertEqual(len(q.candidates), 2)
            r.choose(q, 1)
            self.assertIsNone(r.advance())
            self.assertEqual(r.resolved[slot], OTHER)

    def test_browser_visibility_uniqueness_for_close_open_and_tile(self):
        visible = dict(BROWSER, visible=True, hidden=False)
        hidden = dict(OTHER, visible=False, hidden=True,
                      workspace={'id': -99, 'name': 'special:skipper-tile-1'})
        for phrase, slot in [('close the browser', 'window'),
                             ('open the browser', 'window'),
                             ('open the browser and tile', 'second'),
                             ('tile this window and the browser', 'second')]:
            intent = self.matcher.parse(phrase).intent
            context = {'active': TERM, 'clients': [TERM, visible, hidden]}
            r = WindowResolution(intent, context)
            # A focus/visibility change after capture cannot change the choice.
            context['clients'][1] = dict(visible, visible=False)
            self.assertIsNone(r.advance(), phrase)
            self.assertEqual(r.resolved[slot], visible)
            lone_hidden = WindowResolution(intent, {'active': TERM, 'clients': [TERM, hidden]})
            self.assertIsNone(lone_hidden.advance(), phrase)
            self.assertEqual(lone_hidden.resolved[slot], hidden)

    def test_multiple_visible_or_multiple_hidden_browsers_ask(self):
        for visible in (True, False):
            clients = [dict(BROWSER, visible=visible, hidden=not visible),
                       dict(OTHER, visible=visible, hidden=not visible)]
            r = self.resolution(clients=[TERM] + clients)
            self.assertEqual(r.advance().candidates, tuple(clients))

    def test_unknown_visibility_does_not_hide_ambiguous_candidate(self):
        clients = [dict(BROWSER, visible=True), OTHER]
        r = self.resolution(clients=[TERM] + clients)
        self.assertEqual(r.advance().candidates, tuple(clients))

    def test_missing_and_duplicate_references_do_not_execute(self):
        for phrase, error in [('tile this window and the browser', 'No open window'),
                              ('tile this window and this window', 'same window')]:
            with self.assertRaisesRegex(RuntimeError, error):
                self.resolution(phrase, [TERM]).advance()

    def test_named_windows_and_web_app_exclusion(self):
        self.assertIsNone(self.resolution('tile Project terminal and Docs window').advance())
        app = dict(OTHER, **{'class': 'chrome-discord.com__channels_@me-Default'})
        self.assertIsNone(self.resolution(clients=[TERM, BROWSER, app]).advance())

    def test_incomplete_or_negated_pair_never_falls_back(self):
        for phrase in ['tile this window and', 'tile and the browser',
                       'do not tile this window and the browser']:
            self.assertIsNone(self.matcher.parse(phrase).command)

    def test_runtime_questions_retain_context_and_ignore_old_tokens(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        r = self.resolution(clients=[TERM, BROWSER, OTHER])
        app.resolve_windows(r)
        self.assertEqual(app.state['state'], 'Choose')
        token = app.state['clarification']['choices'][1]['token']
        with patch('runtime.threading.Thread') as worker:
            app.choose_window('stale')
            worker.assert_not_called()
            app.choose_window(token)
            worker.assert_called_once()
        with patch('runtime.tile_selected_windows', return_value='Tiled 2 windows') as tile, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)):
            app.run_tile_pair(r)
            tile.assert_called_once_with(r.context, [TERM, OTHER])
        self.assertIsNone(app.state['clarification'])
        app.choose_window(token)
        self.assertEqual(app.state['state'], 'Ready')

    def test_cancel_invalidates_picker(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        app.resolve_windows(self.resolution(clients=[TERM, BROWSER, OTHER]))
        app.cancel('')
        self.assertIsNone(app.window_resolution)
        self.assertFalse(app.window_choices)
        self.assertIsNone(app.state['clarification'])

    def test_stale_pair_aborts_before_any_dispatch(self):
        for stale in [dict(BROWSER, pid=99), dict(BROWSER, workspace={'id': 2})]:
            with patch('os_actions.run', return_value=json.dumps([TERM, stale])) as run:
                with self.assertRaisesRegex(RuntimeError, 'closed, moved, or changed'):
                    tile_selected_windows({'active': TERM, 'clients': [TERM, BROWSER]}, [TERM, BROWSER])
                run.assert_called_once()

    def test_runtime_routes_pair_without_learning(self):
        app = VoiceRuntime(self.data, self.data / 'status.json')
        context = {'active': TERM, 'clients': [TERM, BROWSER, OTHER]}
        with patch('runtime.save_transcript', return_value=('tile this window and the browser', {})), \
             patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)):
            app.transcribe(self.data / 'test.wav', context, True)
        self.assertEqual(app.state['state'], 'Choose')
        self.assertFalse((self.data / 'aliases.json').exists())

    def test_tiles_only_pair_in_spoken_order_and_moves_remote_browser(self):
        from os_actions import equal_grid
        monitor = dict(id=0, width=1920, height=1080, scale=1, x=0, y=0)
        remote = dict(BROWSER, workspace={'id': 2})
        clients = [TERM, remote, OTHER]
        finals = [dict(w, workspace={'id': 1}, fullscreen=0, fullscreenClient=0,
                       at=list(cell[:2]), size=list(cell[2:]))
                  for w, cell in zip([TERM, remote], equal_grid(2, monitor))]
        responses = [json.dumps(clients), json.dumps([dict(monitor, id=9, x=4000, focused=True), monitor]), json.dumps(clients),
                     'ok', 'ok', 'ok', 'ok', json.dumps([finals[0], remote, OTHER]),
                     json.dumps([finals[0], remote, OTHER]), 'ok', 'ok', 'ok', 'ok', 'ok',
                     json.dumps(finals + [OTHER]), json.dumps(finals + [OTHER]),
                     json.dumps(finals + [OTHER]), 'ok',
                     json.dumps(finals + [dict(OTHER, workspace={'id': -99, 'name': 'special:skipper-tile-1'})]),
                     json.dumps([monitor])]
        with patch('os_actions.run', side_effect=responses) as run:
            self.assertEqual(tile_selected_windows({'active': TERM, 'clients': clients}, [TERM, remote]),
                             'Tiled 2 windows · Minimized 1 other windows (tile all windows to restore)')
        dispatches = [c.args[0][-1] for c in run.call_args_list if 'dispatch' in c.args[0]]
        self.assertTrue(all('address:0x3' not in d for d in dispatches[:-1]))
        self.assertIn('workspace = "special:skipper-tile-1"', dispatches[-1])
        self.assertIn('address:0x3', dispatches[-1])
        self.assertEqual(finals[0]['at'][1], finals[1]['at'][1])
        self.assertLess(finals[0]['at'][0] + finals[0]['size'][0], finals[1]['at'][0])
        self.assertIn('workspace = "1"', dispatches[4])

    def test_specific_browser_intent_precedes_generic_pair(self):
        specific = self.matcher.parse('tile this window and the browser')
        self.assertEqual(specific.intent.type, 'tile_current_window_with_browser')
        self.assertEqual(specific.command, 'windows:tile_current_browser')
        self.assertEqual(specific.selected.label, 'Tile this window and the browser')
        for phrase in ('tile this window and browser', 'tile the current window and the browser'):
            self.assertEqual(self.matcher.parse(phrase).intent, specific.intent)
        generic = self.matcher.parse('tile Project terminal and Docs window')
        self.assertEqual(generic.intent.type, 'tile_pair')
        self.assertNotEqual(generic.command, specific.command)
        r = self.resolution(clients=[TERM, BROWSER, OTHER])
        self.assertEqual(r.advance().prompt, 'Which browser window do you mean?')

    def test_legacy_wording_correction_upgrades_same_references_only(self):
        from corrections import Corrections
        from dataclasses import replace
        from grammar_engine import Intent
        result = self.matcher.parse('tile this window and the browser')
        legacy = replace(result, selected=replace(result.selected, command='windows:tile_pair',
            intent=Intent('tile_pair', result.intent.arguments)))
        corrections = Corrections(self.data / 'corrections.json')
        corrections.save_wording('old phrasing', 'tile this window and the browser',
                                 'tile this window and the browser', legacy)
        parsed = self.matcher.parse('old phrasing')
        self.assertEqual(parsed.intent.type, 'tile_current_window_with_browser')
        self.assertEqual(parsed.method, 'correction')
        wrong = replace(legacy, selected=replace(legacy.selected,
            intent=Intent('tile_pair', (('first', 'the terminal'), ('second', 'the browser')))))
        corrections.save_wording('wrong targets', 'tile this window and the browser',
                                 'tile this window and the browser', wrong)
        self.assertIsNone(self.matcher.parse('wrong targets').intent)

    def test_pair_isolates_workspace_including_new_windows_and_can_restore(self):
        import re
        from copy import deepcopy
        from os_actions import tile_open_windows
        monitor = dict(id=0, width=1920, height=1080, scale=1, x=0, y=0)
        elsewhere = dict(OTHER, address='0x4', stableId='elsewhere', workspace={'id': 3})
        clients = deepcopy([TERM, BROWSER, OTHER, elsewhere])
        context = deepcopy({'active': TERM, 'clients': clients})
        # This window did not exist at the time the command was captured.
        clients.append(dict(OTHER, address='0x5', stableId='new'))
        def run(argv):
            if argv[1] == 'clients':
                return json.dumps(clients)
            if argv[1] == 'monitors':
                return json.dumps([monitor])
            dispatch = argv[-1]
            address = re.search(r'address:(0x[0-9a-f]+)', dispatch).group(1)
            c = next(c for c in clients if c['address'] == address)
            if 'fullscreen_state' in dispatch:
                c.update(fullscreen=0, fullscreenClient=0)
            elif 'window.float' in dispatch:
                c['floating'] = True
            elif 'workspace =' in dispatch:
                destination = re.search(r'workspace = "([^"]+)"', dispatch).group(1)
                c['workspace'] = ({'id': -99, 'name': destination} if destination.startswith('special:')
                                  else {'id': int(destination)})
            elif 'x =' in dispatch:
                x, y = map(int, re.search(r'x = (-?\d+), y = (-?\d+)', dispatch).groups())
                c['size' if 'resize' in dispatch else 'at'] = [x, y]
            return 'ok'
        with patch('os_actions.run', side_effect=run):
            result = tile_selected_windows(context, [TERM, BROWSER])
            self.assertIn('Minimized 2', result)
            self.assertEqual({c['address'] for c in clients if c['workspace']['id'] == 1}, {'0x1', '0x2'})
            self.assertEqual(clients[0]['at'][1], clients[1]['at'][1])
            self.assertLess(clients[0]['at'][0] + clients[0]['size'][0], clients[1]['at'][0])
            self.assertEqual(clients[3], elsewhere)
            tile_open_windows(deepcopy({'active': clients[0], 'clients': clients}))
            self.assertEqual({c['address'] for c in clients if c['workspace']['id'] == 1}, {'0x1', '0x2', '0x3', '0x5'})
            self.assertEqual(clients[3], elsewhere)
