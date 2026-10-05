import json
from contextlib import closing
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import Mock, patch

import personal_store
from intent_matching import IntentMatcher
from runtime import VoiceRuntime
from websites import Websites, browser_domains


class WebsiteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_personal_sites_persist_only_in_private_sqlite(self):
        sites = Websites(self.root)
        sites.save('My project', 'example.com/project')
        sites = Websites(self.root)
        row = next(row for row in sites.view()['sites'] if row['name'] == 'My project')
        self.assertEqual(row['url'], 'https://example.com/project')
        self.assertFalse((self.root/'websites.json').exists())
        db = personal_store.database_path(self.root/'websites.json')
        self.assertEqual(db.stat().st_mode & 0o777, 0o600)
        sites.save('Renamed', 'https://example.org', row['id'])
        self.assertEqual(Websites(self.root).resolve('renamed'), 'https://example.org')
        sites.remove(row['id'])
        self.assertFalse(any(row['name']=='Renamed' for row in Websites(self.root).view()['sites']))

    def test_recents_are_bounded_deduplicated_and_saved_sites_not_repeated(self):
        sites = Websites(self.root)
        for i in range(23): sites.remember(f'https://site{i}.example.com/page?private=query')
        sites.remember('https://site20.example.com/other')
        self.assertEqual(len(sites.view()['recent']), 20)
        self.assertEqual(sites.view()['recent'][0]['url'], 'https://site20.example.com/')
        sites.save('Saved', 'https://site20.example.com/')
        self.assertNotIn('https://site20.example.com/', [row['url'] for row in sites.view()['recent']])

    def test_browser_import_reads_domains_only_and_does_not_change_history(self):
        path=self.root/'History'
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE urls(url TEXT, last_visit_time INTEGER)')
            db.executemany('INSERT INTO urls VALUES (?,?)', [
                ('https://example.com/private/page?token=secret',3),
                ('https://example.com/another',2), ('chrome://settings',1)])
            db.commit()
        before=path.read_bytes()
        self.assertEqual(browser_domains([path]), [dict(id='https://example.com/',name='example.com',url='https://example.com/')])
        self.assertEqual(path.read_bytes(), before)
        with patch('websites.browser_domains') as history:
            Websites(self.root).view()
        history.assert_not_called()

    def test_invalid_site_and_repository_storage_are_rejected(self):
        with self.assertRaises(ValueError): Websites(self.root).save('Bad', 'javascript:alert(1)')
        repo = self.root/'repo'; repo.mkdir(); (repo/'.git').mkdir()
        with self.assertRaisesRegex(ValueError, 'outside a Git checkout'):
            Websites(repo).save('Example', 'https://example.com')

    def app(self):
        app = VoiceRuntime(self.root, self.root/'status.json')
        app.state['monitor'] = 'DP-1'
        app.site_history.refresh = Mock(return_value=dict(most_visited=[], history_message=''))
        return app

    def test_phrase_opens_second_prompt_and_preserves_monitor(self):
        matcher = IntentMatcher(self.root/'aliases.json')
        for phrase in ('open a new browser to web site','open a new browser to a website'):
            result = matcher.parse(phrase)
            self.assertEqual(result.command, 'browser:prompt_website')
            self.assertTrue(result.canonical_plan[0]['arguments']['new_window'])
        app = self.app()
        with patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)), patch('runtime.run_os') as run:
            app.interpret('open a new browser to web site', {'clients':[]})
        run.assert_not_called()
        self.assertEqual(app.state['state'], 'TextEntry')
        self.assertEqual(app.state['written_entry']['kind'], 'website')
        self.assertEqual(app.state['monitor'], 'DP-1')

    def test_saved_site_opens_new_normal_browser_window_and_remembers(self):
        app = self.app(); app.offer_website_entry()
        with patch('runtime.threading.Thread') as thread, patch('runtime.run_os') as run, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)):
            app.submit_url('https://x.com/')
            thread.call_args.kwargs['target']()
        run.assert_called_once_with(['omarchy','launch','browser','--new-window','https://x.com/'])
        self.assertIsNone(app.pending_written)
        self.assertEqual(Websites(self.root).data['recent'][0]['url'], 'https://x.com/')

    def test_manage_requires_current_token_and_preserves_prompt(self):
        app = self.app(); app.offer_website_entry()
        request=dict(token='stale',operation='save',name='Example',url='example.com')
        app.manage_website(json.dumps(request))
        self.assertEqual(len(app.state['written_entry']['sites']), 1)
        request['token']=app.pending_written['token']
        app.manage_website(json.dumps(request))
        self.assertEqual(len(app.state['written_entry']['sites']), 2)
        self.assertEqual(app.state['state'], 'TextEntry')
        with patch('runtime.threading.Thread') as thread:
            app.refresh_written()
        thread.assert_not_called()

    def test_history_refresh_returns_to_same_picker(self):
        app = self.app(); app.offer_website_entry()
        token = app.pending_written['token']
        with patch.object(app.site_history, 'refresh', return_value=dict(most_visited=[dict(id='example.com',name='example.com',url='https://example.com/',visit_count=4)])) as history, \
             patch('runtime.threading.Thread') as thread, \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)):
            app.manage_website(json.dumps(dict(token=token,operation='import_history')))
            thread.call_args.kwargs['target']()
        history.assert_called_once_with(force=True)
        self.assertEqual(app.state['state'], 'TextEntry')
        self.assertEqual(app.pending_written['token'], token)
        self.assertEqual(app.state['written_entry']['most_visited'][0]['url'], 'https://example.com/')

    def test_failed_launch_does_not_remember_and_keeps_picker(self):
        app=self.app(); app.offer_website_entry()
        with patch('runtime.threading.Thread') as thread, patch('runtime.run_os', side_effect=RuntimeError('failed')), \
             patch('runtime.GLib.idle_add', side_effect=lambda fn,*args:fn(*args)):
            app.submit_url('https://example.org')
            thread.call_args.kwargs['target']()
        self.assertEqual(Websites(self.root).data['recent'], [])
        self.assertEqual(app.state['written_entry']['kind'], 'website')
        self.assertIn('failed', app.state['written_entry']['error'])
