from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from intent_matching import IntentMatcher
from runtime import VoiceRuntime
from system_actions import SYSTEM_ACTIONS, SESSION_END_ACTIONS, execute_system


class SystemActionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)

    def test_exact_phrases_and_negation(self):
        matcher=IntentMatcher(self.root/'aliases.json')
        for phrase, action in [('sleep','suspend'),('suspend','suspend'),('lock','lock'),
                               ('screensaver','screensaver'),('log out','logout'),
                               ('reboot','reboot'),('shutdown','shutdown')]:
            result=matcher.parse(phrase)
            self.assertEqual(result.command,'system:'+action)
            self.assertEqual(result.canonical_plan,[{'intent':'system.'+action,'arguments':{}}])
            self.assertIsNone(matcher.parse('do not '+phrase).command)
        self.assertIsNone(matcher.parse('slep').command)

    def test_only_fixed_system_argv_are_launched(self):
        for command, (_, argv) in SYSTEM_ACTIONS.items():
            with patch('system_actions.subprocess.Popen',return_value=Mock(wait=Mock(return_value=0))) as launch:
                self.assertIn('requested',execute_system(command))
            self.assertEqual(launch.call_args.args[0],argv)
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
        with self.assertRaises(ValueError): execute_system('system:unknown')

    def test_failures_and_long_running_launches(self):
        with patch('system_actions.subprocess.Popen',return_value=Mock(wait=Mock(return_value=1))):
            with self.assertRaisesRegex(RuntimeError,'failed'):execute_system('system:suspend')
        with patch('system_actions.subprocess.Popen',return_value=Mock(wait=Mock(side_effect=subprocess.TimeoutExpired('test',.2)))), \
             patch('system_actions.threading.Thread') as thread:
            self.assertIn('requested',execute_system('system:lock'))
        thread.assert_called_once()

    def test_session_ending_actions_require_current_confirmation(self):
        for command in SESSION_END_ACTIONS:
            app=VoiceRuntime(self.root,self.root/'status.json')
            with patch('runtime.GLib.idle_add',side_effect=lambda fn,*args:fn(*args)), patch('runtime.execute_system') as execute:
                app.interpret(command.split(':')[1],{'clients':[]})
                execute.assert_not_called()
                self.assertEqual(app.state['state'],'Confirm')
                token=app.pending[0]
                with patch('runtime.threading.Thread') as thread:
                    app.confirm('stale')
                    thread.assert_not_called()
                app.cancel(token)
                self.assertEqual(app.state['message'],'System action cancelled.')
                execute.assert_not_called()

    def test_confirmation_executes_exactly_once(self):
        app=VoiceRuntime(self.root,self.root/'status.json')
        app.handle_system_action('system:reboot','reboot')
        token=app.pending[0]
        with patch('runtime.threading.Thread') as thread, patch('runtime.execute_system',return_value='Reboot requested.') as execute, \
             patch('runtime.GLib.idle_add',side_effect=lambda fn,*args:fn(*args)):
            app.confirm(token)
            worker=thread.call_args.kwargs
            worker['target'](*worker['args'])
            app.confirm(token)
        thread.assert_called_once()
        execute.assert_called_once_with('system:reboot')

    def test_sleep_dispatches_without_confirmation_and_ends_sequence(self):
        app=VoiceRuntime(self.root,self.root/'status.json')
        app.sequence={'remaining':['anything']}
        with patch('runtime.threading.Thread') as thread, patch('runtime.execute_system',return_value='Suspend requested.') as execute, \
             patch('runtime.GLib.idle_add',side_effect=lambda fn,*args:fn(*args)):
            app.interpret('sleep',{'clients':[]})
            worker=thread.call_args.kwargs
            worker['target'](*worker['args'])
        execute.assert_called_once_with('system:suspend')
        self.assertIsNone(app.pending)
        self.assertIsNone(app.sequence)
