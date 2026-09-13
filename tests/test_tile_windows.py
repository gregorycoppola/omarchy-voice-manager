import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from gui import Keety
from intent_matching import IntentMatcher
from os_actions import tile_open_windows, parse_command

WINDOW = dict(address='0x1', pid=100, stableId='one', **{'class':'foot'}, workspace={'id':2}, mapped=True)


class TileTests(unittest.TestCase):
    def test_phrases(self):
        for phrase in ['Tile open windows!', 'tile all open windows', 'tile windows', 'tile all windows']:
            self.assertEqual(parse_command(phrase), 'windows:tile')

    def test_excludes_keety_and_other_workspaces_and_unmapped_windows(self):
        excluded = [dict(WINDOW,address='0x2', **{'class':'io.github.gregorycoppola.Keety'}),
                    dict(WINDOW,address='0x3',workspace={'id':3}),
                    dict(WINDOW,address='0x4',mapped=False),
                    dict(WINDOW,address='0x5',initialClass='io.github.gregorycoppola.Keety')]
        for initial in [dict(WINDOW,floating=True,fullscreen=2), dict(WINDOW,floating=False,fullscreen=0)]:
            final = dict(WINDOW,floating=False,fullscreen=0,fullscreenClient=0)
            with patch('os_actions.run',side_effect=[json.dumps([initial]+excluded),'ok','ok',json.dumps([final]+excluded)]) as run:
                result = tile_open_windows({'active':WINDOW,'clients':[initial]+excluded})
                self.assertEqual(result,'Tiled 1 windows')
                dispatches = [c.args[0][-1] for c in run.call_args_list if 'dispatch' in c.args[0]]
                self.assertEqual(len(dispatches),2)
                self.assertTrue(all('address:0x1' in d for d in dispatches))
                self.assertIn('internal = 0, client = 0',dispatches[0])
                self.assertIn('action = "off"',dispatches[1])

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
        with patch('os_actions.run',side_effect=[json.dumps([WINDOW]),'ok','ok',json.dumps([dict(WINDOW,floating=True)])]):
            with self.assertRaisesRegex(RuntimeError,'could not confirm'):
                tile_open_windows({'active':WINDOW,'clients':[WINDOW]})

    def test_exact_and_fuzzy_use_original_workspace_context(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            context = {'active':WINDOW,'clients':[WINDOW]}
            app = SimpleNamespace(model=object(),matcher=matcher,finished=Mock(),refresh_aliases=Mock())
            for text in ['tile open windows','tile open windos']:
                with patch('gui.save_transcript',return_value=(text,{'audio_seconds':1,'transcribe_seconds':.1})), patch('gui.tile_open_windows',return_value='Tiled') as tile, patch('gui.GLib.idle_add',side_effect=lambda cb,*args:cb(*args)):
                    Keety.convert(app,Path('test.wav'),commands=True,context=context)
                    tile.assert_called_once_with(context)
                    self.assertEqual(matcher.exact(text),'windows:tile')
