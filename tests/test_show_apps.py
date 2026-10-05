import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from intent_matching import IntentMatcher
from os_actions import show_selected_window, show_all_windows
from runtime import VoiceRuntime
from window_resolution import WindowResolution

VISIBLE = dict(address='0x1', pid=1, stableId='one', workspace={'id':2,'name':'2'}, visible=True, **{'class':'chromium'})
HIDDEN = dict(VISIBLE, workspace={'id':-9,'name':'special:skipper-tile-2'}, visible=False)


class ShowAppsTests(unittest.TestCase):
    def test_show_all_phrases_are_exact_and_select_all(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for phrase, app in [('show all browsers','browser'), ('show all X','x'),
                                ('show all twitter','x'), ('show all terminals','terminal'),
                                ('show all discord','discord'), ('show all file managers','files'),
                                ('show all the open windows','windows')]:
                result = matcher.parse(phrase)
                self.assertEqual(result.command, 'show-all:'+app)
                self.assertEqual(result.canonical_plan, [{'intent':'window.focus','arguments':{'target':{'kind':'all','value':app}}}])
            self.assertIsNone(matcher.parse('do not show all browsers').command)

    def test_show_all_browsers_includes_hidden_and_other_workspaces(self):
        other = dict(VISIBLE, address='0x2', pid=2, stableId='two', focusHistoryID=0,
                     workspace={'id':3,'name':'3'}, **{'class':'firefox'})
        hidden = dict(HIDDEN, focusHistoryID=5)
        x = dict(VISIBLE, address='0x3', **{'class':'chrome-x.com__-Default'})
        with patch('os_actions.show_selected_window') as show:
            message = show_all_windows({'clients':[other,hidden,x]}, 'browser')
        self.assertEqual([call.args[0] for call in show.call_args_list], [hidden,other])
        self.assertIn('2 open browser windows', message)
        with patch('os_actions.show_selected_window') as show:
            show_all_windows({'clients':[other,hidden,x]}, 'x')
        show.assert_called_once_with(x)

    def test_show_all_continues_after_closed_window_and_never_launches(self):
        other = dict(VISIBLE, address='0x2', pid=2, stableId='two')
        with patch('os_actions.show_selected_window', side_effect=[RuntimeError('closed or changed'), 'Shown']) as show:
            message = show_all_windows({'clients':[VISIBLE,other]}, 'browser')
        self.assertEqual(show.call_count, 2)
        self.assertIn('Brought 1', message)
        self.assertIn('Could not show 1', message)
        with patch('os_actions.run') as run, patch('os_actions.launch_desktop') as launch:
            self.assertIn('No open', show_all_windows({'clients':[]}, 'browser'))
        run.assert_not_called()
        launch.assert_not_called()

    def test_phrases_and_hidden_browser_remains_selectable(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for phrase, app in [('show chrome','chrome'),('show chromium','chrome'),('show X','x'),('show twitter','x'),('show the browser','browser')]:
                result = matcher.parse(phrase)
                self.assertEqual(result.canonical_plan,[{'intent':'window.focus','arguments':{'target':{'kind':'application','value':app}}}])
            other = dict(VISIBLE,address='0x2',pid=2,stableId='two')
            resolution = WindowResolution(matcher.parse('show the browser').intent,{'clients':[other,HIDDEN]})
            self.assertEqual(len(resolution.advance().candidates),2)
            self.assertIsNone(matcher.parse('do not show chrome').command)
            with self.assertRaisesRegex(RuntimeError,'No open window'):
                WindowResolution(matcher.parse('show chrome').intent,{'clients':[]}).advance()

    def test_hidden_window_restored_then_raised_and_focused(self):
        with patch('os_actions.run',side_effect=[json.dumps([HIDDEN]),'ok',json.dumps([VISIBLE]),'ok']) as run, \
             patch('os_actions.focus') as focus:
            self.assertIn('Restored',show_selected_window(HIDDEN))
        self.assertIn('workspace = "2"',run.call_args_list[1].args[0][2])
        self.assertIn('alter_zorder',run.call_args_list[3].args[0][2])
        focus.assert_called_once_with(VISIBLE)

    def test_visible_window_not_moved_or_resized_and_replacement_rejected(self):
        with patch('os_actions.run',side_effect=[json.dumps([VISIBLE]),'ok']) as run, patch('os_actions.focus'):
            show_selected_window(VISIBLE)
        self.assertEqual(run.call_count,2)
        self.assertIn('alter_zorder',run.call_args_list[1].args[0][2])
        with patch('os_actions.run',return_value=json.dumps([dict(VISIBLE,pid=99)])) as run, patch('os_actions.focus') as focus:
            with self.assertRaisesRegex(RuntimeError,'closed or changed'):
                show_selected_window(HIDDEN)
            run.assert_called_once()
            focus.assert_not_called()

    def test_show_tiled_window_above_floating_peer(self):
        tiled = dict(VISIBLE, floating=False)
        floating = dict(VISIBLE, address='0x2', pid=2, stableId='two', floating=True)
        with patch('os_actions.run', return_value=json.dumps([tiled, floating])) as run, \
             patch('os_actions.focus') as focus:
            show_selected_window(tiled)
        commands = [call.args[0][2] for call in run.call_args_list[1:]]
        self.assertIn('window.float', commands[0])
        self.assertIn('alter_zorder', commands[1])
        focus.assert_called_once_with(tiled)

    def test_runtime_dispatch_uses_selected_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=IntentMatcher(root/'aliases.json').parse('show chrome')
            resolution=WindowResolution(result.intent,{'clients':[HIDDEN]})
            app=VoiceRuntime(root,root/'status.json')
            with patch('runtime.threading.Thread') as thread:
                app.resolve_windows(resolution)
            self.assertEqual(thread.call_args.kwargs['target'],app.run_show_selection)
            with patch('runtime.show_selected_window',return_value='Restored') as show, \
                 patch('runtime.GLib.idle_add',side_effect=lambda fn,*args:fn(*args)):
                app.run_show_selection(resolution)
            show.assert_called_once_with(HIDDEN)
            self.assertEqual(app.state['state'],'Ready')
