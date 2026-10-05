"""Numbered workspace switching is a supported, searchable intent."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from command_catalog import COMMAND_SUGGESTIONS, INTENTS, STRUCTURED_INTENTS
from intent_matching import IntentMatcher
from os_actions import switch_workspace
from runtime import VoiceRuntime


class SwitchWorkspaceTests(unittest.TestCase):
    def test_all_numbered_workspaces_are_listed_and_parse_to_shared_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            suggestions = {row['command']: row for row in COMMAND_SUGGESTIONS}
            for number in range(1, 11):
                command = f'workspace:switch:{number}'
                self.assertEqual(suggestions[command]['text'], f'switch to workspace {number}')
                self.assertIn(f'go to workspace {number}', suggestions[command]['forms'])
                for phrase in (f'switch to workspace {number}',
                               f'go to workspace {number}'):
                    parsed = matcher.parse(phrase)
                    self.assertEqual(parsed.command, command)
                    self.assertEqual(parsed.canonical_plan, [{'intent': 'workspace.switch',
                                                              'arguments': {'workspace': number}}])
                    self.assertEqual(matcher.parse_instance(parsed.canonical_plan[0]).command, command)
            self.assertEqual(matcher.parse('switch to workspace three').command, 'workspace:switch:3')
            for phrase in ('switch to workspace 0', 'switch to workspace 11',
                           'do not switch to workspace 3'):
                self.assertIsNone(matcher.parse(phrase).command, phrase)
            self.assertTrue(all(command in suggestions or not INTENTS[command]['phrases']
                                for command in STRUCTURED_INTENTS))

    def test_dispatch_and_verify_workspace(self):
        with patch('os_actions.run', side_effect=[json.dumps({'id': 1}), '', json.dumps({'id': 3})]) as run:
            self.assertEqual(switch_workspace(3), 'Switched to workspace 3.')
        self.assertIn('workspace = "3"', run.call_args_list[1].args[0][2])
        with patch('os_actions.run', return_value=json.dumps({'id': 3})) as run:
            self.assertEqual(switch_workspace(3), 'Already on workspace 3.')
            run.assert_called_once()
        for value in (0, 11, True, '3'):
            with self.assertRaises(ValueError):
                switch_workspace(value)

    def test_runtime_executes_workspace_switch(self):
        with patch('runtime.switch_workspace', return_value='Switched') as switch:
            self.assertEqual(VoiceRuntime.execute('workspace:switch:4'), 'Switched')
        switch.assert_called_once_with(4)


if __name__ == '__main__':
    unittest.main()
