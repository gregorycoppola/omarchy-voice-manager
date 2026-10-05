import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from os_actions import move_window_workspace
from runtime import VoiceRuntime

WINDOW = dict(address='0x1', pid=42, stableId='original', workspace={'id':1}, mapped=True, **{'class':'foot'})


class MoveWorkspaceTests(unittest.TestCase):
    def test_number_slot_words_and_invalid_phrases(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher=IntentMatcher(Path(directory)/'aliases.json')
            for number, word in [(3,'3'),(3,'three'),(10,'ten'),(42,'42')]:
                result=matcher.parse('move this window to workspace '+word)
                self.assertEqual(result.command, f'window:move-workspace:{number}')
                self.assertEqual(result.canonical_plan,[{'intent':'window.move_workspace','arguments':{
                    'target':{'kind':'current'},'workspace':{'kind':'id','value':str(number)}}}])
            for text in ['move this window to workspace 0','move this window to workspace -1',
                         'do not move this window to workspace 3','move this window to workspace',
                         'move this window to workspace 3; reboot']:
                self.assertIsNone(matcher.parse(text).command, text)

    def test_move_original_window_and_verify_destination(self):
        moved=dict(WINDOW,workspace={'id':3})
        with patch('os_actions.require_layout_allowed'), patch('os_actions.run',side_effect=[json.dumps([WINDOW]),'',json.dumps([moved])]) as run:
            self.assertIn('workspace 3',move_window_workspace(WINDOW,3))
        dispatch=run.call_args_list[1].args[0]
        self.assertIn('address:0x1',dispatch[2])
        self.assertIn('workspace = "3", follow = false',dispatch[2])

    def test_replacement_and_unconfirmed_move_rejected(self):
        with patch('os_actions.require_layout_allowed'), patch('os_actions.run',return_value=json.dumps([dict(WINDOW,pid=99)])) as run:
            with self.assertRaisesRegex(RuntimeError,'closed or changed'):move_window_workspace(WINDOW,3)
            run.assert_called_once()
        with patch('os_actions.require_layout_allowed'), patch('os_actions.run',side_effect=[json.dumps([WINDOW]),'',json.dumps([WINDOW])]):
            with self.assertRaisesRegex(RuntimeError,'confirm'):move_window_workspace(WINDOW,3)

    def test_same_workspace_and_invalid_numbers_do_not_move(self):
        with patch('os_actions.require_layout_allowed'), patch('os_actions.run',return_value=json.dumps([WINDOW])) as run:
            self.assertIn('already',move_window_workspace(WINDOW,1))
            run.assert_called_once()
        for value in [0,-1,True,'3',1000000000]:
            with self.assertRaises(ValueError):move_window_workspace(WINDOW,value)

    def test_grouped_window_detached_before_move(self):
        grouped=dict(WINDOW,grouped=['0x1','0x2'])
        with patch('os_actions.require_layout_allowed'), patch('os_actions.run',side_effect=[json.dumps([grouped]),'','',json.dumps([dict(WINDOW,workspace={'id':3})])]) as run:
            move_window_workspace(grouped,3)
        self.assertIn('out_of_group = true',run.call_args_list[1].args[0][2])

    def test_runtime_uses_captured_window(self):
        with patch('runtime.move_window_workspace',return_value='Moved') as move:
            VoiceRuntime.execute('window:move-workspace:3',{'active':WINDOW})
        move.assert_called_once_with(WINDOW,3)
