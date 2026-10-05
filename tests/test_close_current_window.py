"""Closing the current window must retain the command's captured identity."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from intent_matching import IntentMatcher
from runtime import VoiceRuntime

WINDOW = dict(address='0x1', pid=42, stableId='original', mapped=True,
              **{'class': 'foot'})


class CloseCurrentWindowTests(unittest.TestCase):
    def test_phrases_and_canonical_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for phrase in ('close this window', 'close the current window',
                           'close current window', 'close this winodw'):
                result = matcher.parse(phrase)
                self.assertEqual(result.command, 'close:current_window')
                self.assertEqual(result.method, 'exact')
                self.assertEqual(result.canonical_plan, [{'intent': 'window.close',
                    'arguments': {'target': {'kind': 'current'}}}])
                self.assertEqual(matcher.parse_instance(result.canonical_plan[0]).command,
                                 result.command)
            self.assertIsNone(matcher.parse('do not close this window').command)

    def test_closes_only_captured_window(self):
        other = dict(WINDOW, address='0x2', pid=99, stableId='other')
        with patch('os_actions.run', side_effect=[json.dumps([other, WINDOW]), '',
                                                  json.dumps([other])]) as run:
            VoiceRuntime.execute('close:current_window', {'active': WINDOW})
        self.assertEqual(run.call_args_list[1].args[0], ['hyprctl', 'dispatch',
            'hl.dsp.window.close({ window = "address:0x1" })'])

    def test_missing_or_replaced_window_never_closes_another(self):
        with patch('os_actions.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'No focused window'):
                VoiceRuntime.execute('close:current_window', {})
            run.assert_not_called()
        with patch('os_actions.run', return_value=json.dumps([
                dict(WINDOW, stableId='replacement')])) as run:
            with self.assertRaisesRegex(RuntimeError, 'closed or changed'):
                VoiceRuntime.execute('close:current_window', {'active': WINDOW})
            run.assert_called_once()
