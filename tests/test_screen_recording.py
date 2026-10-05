import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from settings import Settings
from intent_matching import IntentMatcher
import screen_recording as recording


class RecordingTests(unittest.TestCase):
    def setUp(self):
        recording._PENDING = None

    def test_dataset_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for text, action in [('start a screen recording','start'),('stop recording','stop')]:
                result = matcher.parse(text)
                self.assertEqual(result.command, 'screenrecord:'+action)
                self.assertEqual(result.canonical_plan[0]['intent'], 'screen_recording.'+action)

    def test_explicit_webcam_phrases(self):
        with tempfile.TemporaryDirectory() as directory:
            matcher = IntentMatcher(Path(directory)/'aliases.json')
            for mode, enabled in [('with', True), ('without', False)]:
                for camera in ('web cam', 'webcam'):
                    result = matcher.parse(f'start a new screen recording {mode} {camera} capture')
                    self.assertEqual(result.command, 'screenrecord:start' if enabled else 'screenrecord:start_without_webcam')
                    self.assertEqual(result.canonical_plan[0]['arguments']['webcam'], enabled)
            self.assertIsNone(matcher.parse('do not start a new screen recording with webcam capture').command)

    def test_duplicate_start_and_idle_stop_do_not_toggle(self):
        for action, state in [('start',True), ('start_without_webcam',True), ('stop',False)]:
            with patch.object(recording,'active',return_value=state), patch.object(recording.subprocess,'Popen') as popen:
                recording.execute_recording(action, Mock())
                popen.assert_not_called()

    def test_start_uses_private_monitor_then_webcam_and_mic(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            settings=Settings(path/'settings.json')
            settings.set_screen_recording_monitor('example-output')
            settings.set_confirm_terminal_close(False)
            settings.set_layout_excluded_classes(['example.overlay'])
            self.assertEqual(Settings(path/'settings.json').screen_recording_monitor,'example-output')
            run=Mock(return_value=json.dumps([{'name':'example-output'}]))
            with patch.object(recording,'DEFAULT_DATA',path), patch.object(recording,'active',side_effect=[False,True]), patch.object(recording.subprocess,'Popen') as popen, patch.object(recording.threading,'Thread'):
                self.assertIn('started',recording.execute_recording('start',run))
                self.assertIn('example-output', run.call_args.args[0][2])
                self.assertEqual(popen.call_args.args[0],['omarchy','screenrecord','--fullscreen','--with-webcam','--with-microphone-audio'])

    def test_without_webcam_keeps_microphone(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(recording, 'DEFAULT_DATA', Path(directory)), patch.object(recording, 'active', side_effect=[False, True]), patch.object(recording.subprocess, 'Popen') as popen, patch.object(recording.threading, 'Thread'):
                self.assertIn('without webcam', recording.execute_recording('start_without_webcam', Mock()))
                self.assertEqual(popen.call_args.args[0], ['omarchy', 'screenrecord', '--fullscreen', '--with-microphone-audio'])

    def test_stop_uses_explicit_stop_and_reports_saving(self):
        with patch.object(recording,'active',side_effect=[True,False]), patch.object(recording.subprocess,'Popen') as popen, patch.object(recording.threading,'Thread'):
            self.assertIn('saving',recording.execute_recording('stop',Mock()))
            self.assertEqual(popen.call_args.args[0],['omarchy','screenrecord','--stop-recording'])
            popen.return_value.poll.return_value=None
            with self.assertRaisesRegex(RuntimeError,'saving'):
                recording.execute_recording('start',Mock())

    def test_disconnected_preference_blocks_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            Settings(path/'settings.json').set_screen_recording_monitor('missing')
            with patch.object(recording,'DEFAULT_DATA',path), patch.object(recording,'active',return_value=False), patch.object(recording.subprocess,'Popen') as popen:
                with self.assertRaisesRegex(RuntimeError,'not connected'):
                    recording.execute_recording('start',Mock(return_value='[]'))
                popen.assert_not_called()
