import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from gui import Skipper
from intent_matching import IntentMatcher
from os_actions import tile_open_windows, parse_command, equal_grid

WINDOW = dict(address='0x1', pid=100, stableId='one', **{'class':'foot'}, workspace={'id':2}, mapped=True, monitor=1)

MONITOR = dict(id=1, width=1920, height=1080, scale=1, x=1280, y=0, reserved=[0,26,0,0])

class TileTests(unittest.TestCase):
    def test_equal_cells_scaling_rotation_and_odd_counts(self):
        for monitor in [MONITOR, dict(MONITOR,width=2560,height=1600,scale=2,x=-1280), dict(MONITOR,transform=1)]:
            for count in range(1,10):
                cells = equal_grid(count,monitor)
                self.assertEqual(len(cells),count)
                self.assertEqual(len({(w,h) for x,y,w,h in cells}),1)
                for i,(x,y,w,h) in enumerate(cells):
                    for xx,yy,ww,hh in cells[i+1:]:
                        self.assertTrue(x+w<=xx or xx+ww<=x or y+h<=yy or yy+hh<=y)
        cells = equal_grid(4,MONITOR)
        self.assertEqual(len({x for x,y,w,h in cells}),2)
        self.assertEqual(len({y for x,y,w,h in cells}),2)

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

    def test_exact_and_fuzzy_use_original_workspace_context(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            context = {'active':WINDOW,'clients':[WINDOW]}
            app = SimpleNamespace(model=object(),matcher=matcher,finished=Mock(),refresh_aliases=Mock())
            for text in ['tile open windows','tile open windos']:
                with patch('gui.save_transcript',return_value=(text,{'audio_seconds':1,'transcribe_seconds':.1})), patch('gui.tile_open_windows',return_value='Tiled') as tile, patch('gui.GLib.idle_add',side_effect=lambda cb,*args:cb(*args)):
                    Skipper.convert(app,Path('test.wav'),commands=True,context=context)
                    tile.assert_called_once_with(context)
                    self.assertEqual(matcher.exact(text),'windows:tile')
