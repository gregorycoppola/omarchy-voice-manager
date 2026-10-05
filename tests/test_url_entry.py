import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import VoiceRuntime
from url_entry import normalize_url


class UrlEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = VoiceRuntime(self.root, self.root / 'status.json')
        for context in [patch('runtime.GLib.idle_add', side_effect=lambda fn, *args: fn(*args)),
                        patch.object(self.app, 'focused_monitor', return_value='eDP-1')]:
            context.start()
            self.addCleanup(context.stop)

    def test_command_opens_url_prompt_without_launching(self):
        with patch('runtime.run_os') as run:
            self.app.interpret('open url', {'clients': []})
        run.assert_not_called()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.assertEqual(self.app.state['written_entry']['kind'], 'url')
        self.assertEqual(self.app.state['written_entry']['suggestions'], [])
        with patch('runtime.threading.Thread') as thread:
            self.app.refresh_written()
        thread.assert_not_called()

    def test_submit_opens_address_as_one_argument(self):
        self.app.offer_url_entry()
        token = self.app.pending_written['token']
        with patch('runtime.threading.Thread') as thread, patch('runtime.run_os') as run:
            self.app.submit_written(json.dumps(dict(token=token, text='example.com/a?x=1&y=2')))
            thread.call_args.kwargs['target']()
        run.assert_called_once_with(['omarchy', 'launch', 'browser', 'https://example.com/a?x=1&y=2'])
        self.assertIsNone(self.app.pending_written)
        self.assertEqual(self.app.state['state'], 'Ready')

    def test_invalid_address_keeps_prompt_and_cancel_clears_sequence(self):
        self.app.offer_url_entry()
        token = self.app.pending_written['token']
        with patch('runtime.run_os') as run:
            self.app.submit_written(json.dumps(dict(token=token, text='javascript:alert(1)')))
        run.assert_not_called()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.assertTrue(self.app.state['written_entry']['error'])
        self.app.sequence = {'remaining': ['open chrome']}
        self.app.cancel(token)
        self.assertIsNone(self.app.pending_written)
        self.assertIsNone(self.app.sequence)

    def test_stale_token_does_not_submit(self):
        self.app.offer_url_entry()
        with patch.object(self.app, 'submit_url') as submit:
            self.app.submit_written(json.dumps(dict(token='stale', text='example.com')))
        submit.assert_not_called()

    def test_browser_failure_keeps_address_for_retry(self):
        self.app.offer_url_entry()
        with patch('runtime.threading.Thread') as thread, patch('runtime.run_os', side_effect=RuntimeError('launcher failed')):
            self.app.submit_url('example.com')
            thread.call_args.kwargs['target']()
        self.assertEqual(self.app.state['state'], 'TextEntry')
        self.assertEqual(self.app.state['written_entry']['text'], 'example.com')
        self.assertIn('launcher failed', self.app.state['written_entry']['error'])

    def test_address_validation(self):
        for text, expected in [(' example.com ', 'https://example.com'),
                               ('http://localhost:8080/test', 'http://localhost:8080/test'),
                               ('localhost:8080/test', 'https://localhost:8080/test')]:
            self.assertEqual(normalize_url(text), expected)
        for text in ['', None, 'https://', 'file:///etc/passwd', 'javascript:alert(1)',
                     '--private', 'https://example.com:bad', 'hello world', 'https://user:pass@example.com']:
            with self.assertRaises(ValueError, msg=repr(text)):
                normalize_url(text)
