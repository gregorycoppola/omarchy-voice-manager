"""Provider checks use temporary data and mocked system actions."""
from pathlib import Path
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
import audio_devices
import file_search
import system_controls

class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.data = self.home / 'data'
        self.data.mkdir()
        env = patch.dict(os.environ, XDG_DATA_HOME=str(self.data), XDG_STATE_HOME=str(self.home/'state'))
        env.start(); self.addCleanup(env.stop)

    def test_recent_order_and_no_filename_scan(self):
        first = self.home/'first.txt'; first.write_text('one')
        second = self.home/'second.txt'; second.write_text('two')
        (self.data/'recently-used.xbel').write_text(f'<xbel><bookmark href="{first.as_uri()}" visited="2020-01-01T00:00:00Z"/></xbel>')
        file_search.remember_open(second)
        with patch('file_search.subprocess.Popen') as process:
            rows, limited = file_search.search('', threading.Event(), self.home)
        self.assertEqual([r['label'] for r in rows], ['second.txt','first.txt'])
        process.assert_not_called()
        self.assertFalse(limited)
        self.assertEqual(file_search.recent_database().stat().st_mode & 0o777, 0o600)

    def test_changed_file_never_opens(self):
        path=self.home/'file.txt'; path.write_text('old')
        captured=file_search.identity(path); path.write_text('changed content')
        with patch('file_search.subprocess.Popen') as process:
            with self.assertRaises(RuntimeError): file_search.open_file(captured)
        process.assert_not_called()

    def test_open_passes_literal_path_and_remembers(self):
        path=self.home/'a $(unsafe); file.txt'; path.write_text('text')
        with patch('file_search.subprocess.Popen') as process:
            file_search.open_file(file_search.identity(path))
        self.assertEqual(process.call_args.args[0], ['xdg-open',str(path)])
        self.assertEqual(file_search.search('',threading.Event(),self.home)[0][0]['label'],path.name)

    def test_filename_search(self):
        (self.home/'invoice draft.txt').write_text('text')
        (self.home/'.private.txt').write_text('text')
        rows,_=file_search.search('invoice',threading.Event(),self.home)
        self.assertEqual([r['label'] for r in rows],['invoice draft.txt'])
        self.assertEqual(file_search.search('private',threading.Event(),self.home)[0],[])

class AudioTests(unittest.TestCase):
    def test_recycled_device_is_rejected(self):
        old=dict(direction='output',name='speaker',serial='1')
        new=dict(old,serial='2')
        with patch('audio_devices.snapshot',return_value=[dict(identity=new,current=False)]), patch('audio_devices.call') as call:
            with self.assertRaises(RuntimeError): audio_devices.set_default(old)
        call.assert_not_called()

    def test_already_default_no_mutation(self):
        target=dict(direction='input',name='mic',serial='1')
        with patch('audio_devices.snapshot',return_value=[dict(identity=target,current=True,label='Mic')]), patch('audio_devices.call') as call:
            self.assertIn('already',audio_devices.set_default(target))
        call.assert_not_called()

class ControlsTests(unittest.TestCase):
    def test_wifi_enable_is_idempotent(self):
        with patch('system_controls.run',return_value='enabled') as run:
            system_controls.execute(dict(kind='wifi',enabled=True))
        self.assertTrue(all(c.args==('nmcli','radio','wifi') for c in run.call_args_list))

    def test_wifi_disable_sets_explicit_state(self):
        with patch('system_controls.run',side_effect=['enabled','','disabled']) as run:
            system_controls.execute(dict(kind='wifi',enabled=False))
        self.assertIn(('nmcli','radio','wifi','off'),[c.args for c in run.call_args_list])

    def test_nightlight_already_on_does_not_toggle(self):
        with patch('system_controls.night_state',return_value=True), patch('system_controls.run') as run:
            system_controls.execute(dict(kind='night-light',enabled=True))
        run.assert_not_called()

if __name__=='__main__': unittest.main()
