import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import VoiceRuntime


class ImmediateThread:
    def __init__(self, target, args=(), kwargs=None, **unused):
        self.target, self.args, self.kwargs = target, args, kwargs or {}
    def start(self):
        self.target(*self.args, **self.kwargs)


class SequenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.app = VoiceRuntime(root, root / 'status.json')
        self.first = {'active': {'address': '0x1'}, 'clients': []}
        self.later = {'active': {'address': '0x2'}, 'clients': []}
        for mock in (patch('runtime.GLib.idle_add', side_effect=lambda fn, *a: fn(*a)),
                     patch('runtime.threading.Thread', ImmediateThread),
                     patch.object(self.app, 'focused_monitor', return_value='screen')):
            mock.start()
            self.addCleanup(mock.stop)
        with patch('runtime.capture_window_context', return_value=self.first):
            self.app.type_command()

    def submit(self, steps):
        self.app.submit_written(json.dumps({'token': self.app.pending_written['token'], 'steps': steps}))

    def test_order_and_fresh_context_after_previous_action(self):
        events = []
        def execute(command, context=None, target=None):
            events.append(command)
            self.assertEqual(context, self.first if command == 'browser_fullscreen' else self.later)
            return 'Done'
        def capture():
            self.assertEqual(events, ['browser_fullscreen'])
            return self.later
        with patch.object(self.app, 'execute', side_effect=execute), patch('runtime.capture_window_context', side_effect=capture):
            self.submit(['bring up chrome', 'tile the windows'])
        self.assertEqual(events, ['browser_fullscreen', 'windows:tile'])
        self.assertIsNone(self.app.sequence)
        self.assertIn('Finished 2 commands', self.app.state['message'])
        self.assertEqual(self.app.command_store.recent(), ['tile the windows', 'bring up chrome'])

    def test_invalid_step_prevents_any_execution(self):
        with patch.object(self.app, 'execute') as execute:
            self.submit(['bring up chrome', 'purple asparagus dances'])
        execute.assert_not_called()
        self.assertIn('Step 2', self.app.state['written_entry']['error'])
        self.assertIsNone(self.app.sequence)

    def test_error_stops_remaining_steps(self):
        with patch.object(self.app, 'execute', side_effect=RuntimeError('failed')) as execute:
            self.submit(['bring up chrome', 'tile the windows'])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.app.state['state'], 'Error')
        self.assertIsNone(self.app.sequence)

    def test_confirmation_pauses_then_resumes_and_cancel_stops(self):
        target = dict(address='0x1', pid=1, stableId='one', **{'class': 'foot'})
        with patch('runtime.terminal_close_target', return_value=target), \
             patch('runtime.terminal_has_jobs', return_value=True), \
             patch.object(self.app, 'execute', return_value='Done') as execute, \
             patch('runtime.capture_window_context', return_value=self.later):
            self.submit(['close terminal', 'tile the windows'])
            execute.assert_not_called()
            self.assertEqual(self.app.state['state'], 'Confirm')
            self.app.confirm(self.app.pending[0])
            self.assertEqual([c.args[0] for c in execute.call_args_list], ['close:terminal', 'windows:tile'])
            self.app.type_command()
            execute.reset_mock()
            self.submit(['close terminal', 'tile the windows'])
            self.app.cancel(self.app.pending[0])
            execute.assert_not_called()
            self.assertIsNone(self.app.sequence)

    def test_replaced_named_target_stops_queue_without_retargeting(self):
        original = dict(address='0x1', pid=1, stableId='one', title='Unique project', **{'class': 'foot'})
        self.app.pending_written['context']['clients'] = [original]
        changed = dict(original, pid=2, stableId='replacement')
        with patch.object(self.app, 'execute', return_value='Done') as execute, \
             patch('runtime.capture_window_context', return_value={'clients': [changed]}):
            self.submit(['bring up chrome', 'close the unique project terminal'])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.app.state['state'], 'Error')
        self.assertIsNone(self.app.sequence)
