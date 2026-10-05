import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from intent_matching import IntentMatcher
from os_actions import tile_open_windows, parse_command, equal_grid

WINDOW = dict(address='0x1', pid=100, stableId='one', **{'class':'foot'}, workspace={'id':2}, mapped=True, monitor=1)

MONITOR = dict(id=1, width=1920, height=1080, scale=1, x=1280, y=0, reserved=[0,26,0,0])

class TileTests(unittest.TestCase):
    def test_equal_cells_scaling_rotation_and_odd_counts(self):
        for monitor in [MONITOR, dict(MONITOR,width=2560,height=1600,scale=2,x=-1280), dict(MONITOR,transform=1)]:
            for count in range(1,9):
                cells = equal_grid(count,monitor)
                self.assertEqual(len(cells),count)
                self.assertEqual(len({(w,h) for x,y,w,h in cells}),1)
                for i,(x,y,w,h) in enumerate(cells):
                    for xx,yy,ww,hh in cells[i+1:]:
                        self.assertTrue(x+w<=xx or xx+ww<=x or y+h<=yy or yy+hh<=y)
        cells = equal_grid(4,MONITOR)
        self.assertEqual(len({x for x,y,w,h in cells}),2)
        self.assertEqual(len({y for x,y,w,h in cells}),2)

    def test_side_by_side_on_scaled_laptop_and_minimum_size(self):
        laptop = dict(MONITOR, width=2560, height=1600, scale=2)
        with self.assertRaisesRegex(RuntimeError, 'equal grid'):
            equal_grid(200, laptop)
        first, second = equal_grid(2, laptop)
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[2], 622)
        self.assertGreater(second[0], first[0] + first[2])

    def test_five_windows_use_equal_wide_cells(self):
        laptop = dict(MONITOR, width=2560, height=1600, scale=2, x=0)
        cells = equal_grid(5, laptop)
        self.assertEqual([len([c for c in cells if c[1] == y])
                          for y in sorted({c[1] for c in cells})], [2, 2, 1])
        self.assertEqual([c[2] for c in cells], [622, 622, 622, 622, 622])
        for y in {c[1] for c in cells}:
            row = [c for c in cells if c[1] == y]
            self.assertEqual(row[0][0], 12)
            if len(row) == 2:
                self.assertLessEqual(1280 - (row[-1][0] + row[-1][2]), 13)

    def test_phrases(self):
        for phrase in ['Tile open windows!', 'tile all open windows', 'tile windows', 'tile all windows']:
            self.assertEqual(parse_command(phrase), 'windows:tile')

    def test_excludes_skipper_and_other_workspaces_and_unmapped_windows(self):
        excluded = [dict(WINDOW,address='0x2', **{'class':'io.github.gregorycoppola.Skipper'}),
                    dict(WINDOW,address='0x3',workspace={'id':3}),
                    dict(WINDOW,address='0x4',mapped=False),
                    dict(WINDOW,address='0x5',initialClass='io.github.gregorycoppola.Skipper')]
        for initial in [dict(WINDOW,floating=True,fullscreen=2), dict(WINDOW,floating=False,fullscreen=0)]:
            x,y,w,h = equal_grid(1,MONITOR)[0]
            final = dict(WINDOW,floating=True,fullscreen=0,fullscreenClient=0,at=[x,y],size=[w,h])
            with patch('os_actions.run',side_effect=[json.dumps([initial]+excluded),json.dumps([MONITOR]),json.dumps([initial]+excluded),'ok','ok','ok','ok',json.dumps([final]+excluded)]) as run:
                result = tile_open_windows({'active':WINDOW,'clients':[initial]+excluded})
                self.assertEqual(result,'Tiled 1 windows')
                dispatches = [c.args[0][-1] for c in run.call_args_list if 'dispatch' in c.args[0]]
                self.assertEqual(len(dispatches),4)
                self.assertTrue(all('address:0x1' in d for d in dispatches))
                self.assertIn('internal = 0, client = 0',dispatches[0])
                self.assertIn('action = "on"',dispatches[1])

    def test_stale_targets_never_dispatch(self):
        for clients in [[], [dict(WINDOW,pid=101)], [dict(WINDOW,workspace={'id':3})]]:
            with patch('os_actions.run',return_value=json.dumps(clients)) as run:
                self.assertIn('Skipped 1',tile_open_windows({'active':WINDOW,'clients':[WINDOW]}))
                run.assert_called_once()

    def test_missing_context_and_empty_workspace(self):
        with patch('os_actions.run') as run:
            with self.assertRaises(RuntimeError):
                tile_open_windows(None)
            self.assertIn('No open windows',tile_open_windows({'active':WINDOW,'clients':[]}))
            run.assert_not_called()

    def test_failed_dispatch_state_is_reported(self):
        with patch('os_actions.run',side_effect=[json.dumps([WINDOW]),json.dumps([MONITOR]),json.dumps([WINDOW]),'ok','ok','ok','ok']+[json.dumps([dict(WINDOW,floating=True)])]*10):
            with patch('os_actions.time.sleep'), self.assertRaisesRegex(RuntimeError,'could not confirm'):
                tile_open_windows({'active':WINDOW,'clients':[WINDOW]})


    def test_show_raises_windows_and_tile_still_tiles(self):
        from runtime import VoiceRuntime
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            expected = matcher.parse('tile all windows').intent
            context = {'active': WINDOW, 'clients': [WINDOW]}
            for phrase in ('show all windows', 'show all open windows', 'show all open window'):
                result = matcher.parse(phrase)
                self.assertNotEqual(result.intent, expected)
                self.assertEqual(result.command, 'show-all:windows')
                with patch('runtime.show_all_windows', return_value='Shown') as show:
                    VoiceRuntime.execute(result.command, context)
                    show.assert_called_once_with(context, 'windows')
            with patch('runtime.tile_open_windows', return_value='Tiled') as tile:
                VoiceRuntime.execute('windows', context)
                tile.assert_called_once_with(context)
