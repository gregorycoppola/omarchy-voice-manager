"""Desktop actions preserve intent, target, and truthful failure reporting."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from desktop_commands import DESKTOP_COMMANDS, execute_desktop
from intent_matching import IntentMatcher
from runtime import VoiceRuntime


class DesktopTests(unittest.TestCase):
    def test_phrases_and_negation(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory) / 'aliases.json')
            for command, (_, phrases) in DESKTOP_COMMANDS.items():
                for phrase in phrases:
                    self.assertEqual(matcher.parse(phrase).command, command)
                    self.assertIsNone(matcher.parse('do not ' + phrase).command)
            self.assertNotEqual(matcher.parse('mute').intent, matcher.parse('unmute').intent)

    def test_explicit_mute_is_idempotent_and_verified(self):
        for action, value, response in [('mute', '1', 'Mute: yes'), ('unmute', '0', 'Mute: no')]:
            run = Mock(side_effect=['physical-sink\n', '', response])
            execute_desktop('volume:' + action, run)
            self.assertEqual(run.call_args_list[1].args[0], ['pactl', 'set-sink-mute', 'physical-sink', value])
        with self.assertRaisesRegex(RuntimeError, 'confirm'):
            execute_desktop('volume:mute', Mock(side_effect=['sink', '', 'Mute: no']))

    def test_brightness_preserves_capture_and_rejects_missing_display(self):
        monitors = [dict(id=0, name='eDP-1', focused=False), dict(id=1, name='DP-1', focused=True)]
        run = Mock(side_effect=[json.dumps(monitors), ''])
        execute_desktop('brightness:down', run, {'active': {'monitor': 0}})
        self.assertEqual(run.call_args.args[0], ['omarchy', 'brightness', 'display', '--monitor', 'eDP-1', '5%-'])
        run = Mock(return_value=json.dumps(monitors))
        with self.assertRaisesRegex(RuntimeError, 'no longer available'):
            execute_desktop('brightness:up', run, {'active': {'monitor': 9}})
        run.assert_called_once()

    def test_missing_player_and_backend_failure_are_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'No media player'):
            execute_desktop('media:pause', Mock(return_value='unhandled\n'))
        with self.assertRaisesRegex(RuntimeError, 'backend failed'):
            execute_desktop('volume:up', Mock(side_effect=RuntimeError('backend failed')))
        run = Mock(return_value='ok\n')
        self.assertEqual(execute_desktop('media:next', run), 'Next track requested')
        run.assert_called_once_with(['omarchy-shell', 'media', 'next'])

    def test_speech_and_written_use_same_desktop_executor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = VoiceRuntime(root, root / 'status.json')
            context = {'active': {'monitor': 0}}
            for source in ['speech', 'written']:
                with patch('runtime.execute_desktop', return_value='Done') as execute, \
                     patch('runtime.GLib.idle_add', side_effect=lambda fn, *a: fn(*a)):
                    app.interpret('brightness up', context, source=source)
                self.assertEqual(execute.call_args.args[0], 'brightness:up')
                self.assertEqual(execute.call_args.args[2], context)
                self.assertEqual(app.state['state'], 'Ready')
