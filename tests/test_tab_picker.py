import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runtime import VoiceRuntime

class TabPickerTests(unittest.TestCase):
    def test_listing_preserves_tab_identity_and_returns_separate_list(self):
        with tempfile.TemporaryDirectory() as folder:
            app = VoiceRuntime(data=Path(folder), status_path=Path(folder)/'status.json')
            tab = dict(tabId=12,windowId=4,title='Docs',url='https://example.com/docs',index=0,active=True)
            def dispatch(fn,*args): return fn(*args)
            with patch('runtime.connection.tab_picker', return_value={'tabs':[tab]}) as call, patch('runtime.GLib.idle_add',side_effect=dispatch), patch.object(app,'publish'), patch.object(app,'focused_monitor',return_value='test'):
                app.load_browser_tabs()
            call.assert_called_once_with()
            self.assertEqual(app.state['state'],'WindowList')
            self.assertEqual(app.state['list_kind'],'tabs')
            self.assertEqual(app.state['window_list'][0]['browser_tab'],tab)
            self.assertEqual(app.state['window_list'][0]['app'],'example.com')
            with patch('runtime.connection.tab_picker',return_value={'focused':True}) as focus, patch('runtime.GLib.idle_add'):
                app.finish_focus_browser_tab(app.state['window_list'][0])
            focus.assert_called_once_with(tab)

    def test_unknown_choice_never_contacts_browser(self):
        with tempfile.TemporaryDirectory() as folder:
            app=VoiceRuntime(data=Path(folder),status_path=Path(folder)/'status.json')
            app.state.update(state='WindowList',window_list=[])
            with patch('runtime.connection.tab_picker') as browser:
                app.focus_listed_window('invented')
            browser.assert_not_called()
