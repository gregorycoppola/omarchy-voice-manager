from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from speech import openai_fallback
from speech.grammar import Grammar
from speech_preview import Preview


class OpenAIFallbackTests(unittest.TestCase):
    def setUp(self):
        self.audit=patch("speech.openai_fallback.audit.append").start()
        self.addCleanup(patch.stopall)

    def test_canonical_interpretation_is_validated_locally(self):
        reply={'status':'interpreted','canonical_text':'volume down','clarification':None}
        parsed=openai_fallback.validate(reply,Grammar({}))
        self.assertEqual(parsed['candidates'][0]['intent']['arguments'],{'action':'volume:down'})
        reply['canonical_text']='delete every file'
        with self.assertRaises(ValueError):openai_fallback.validate(reply,Grammar({}))

    def test_no_match_routes_both_sources_but_not_matches_empty_or_disabled(self):
        for source in ('typed','microphone'):
            for text,enabled,expected in [('make it quieter',True,True),('volume down',True,False),
                                          ('',True,False),('make it quieter',False,False)]:
                with self.subTest(source=source,text=text,enabled=enabled),closing(sqlite3.connect(':memory:')) as db:
                    db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY, created TEXT, data TEXT, review TEXT, intended TEXT)')
                    grammar=Grammar({})
                    fake=SimpleNamespace(db=db,phase='ready',generation=1,intended=Mock(),render_result=Mock(),
                        cloud=Mock(),run_fallback=Mock(),history_label=Mock())
                    fake.cloud.get_active.return_value=enabled
                    observation={'id':'test','source':source,'parsed':grammar.parse(text)}
                    with patch('speech_preview.threading.Thread') as thread:
                        Preview.show_result(fake,observation,1,grammar)
                    self.assertEqual(thread.called,expected)
                    if expected:
                        thread.assert_called_once()
                        saved=json.loads(db.execute('SELECT data FROM observations').fetchone()[0])
                        self.assertEqual(saved['input']['text'],text)
                        self.assertEqual(saved['outcome']['status'],'checking_openai')

    def test_response_does_not_replace_original_parse_or_selected_history(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE observations(id TEXT PRIMARY KEY, created TEXT, data TEXT, review TEXT, intended TEXT)')
            grammar=Grammar({});original=grammar.parse('volume dawn')
            observation={'id':'a','source':'typed','parsed':original}
            result={'status':'interpreted','parsed':grammar.parse('volume down')}
            fake=SimpleNamespace(db=db,phase='ready',latest='another',render_result=Mock(),history_label=Mock())
            Preview.finish_fallback(fake,observation,result)
            fake.render_result.assert_not_called()
            saved=json.loads(db.execute('SELECT data FROM observations').fetchone()[0])
            self.assertEqual(saved['parsed'],original)
            self.assertEqual(saved['input']['text'],'volume dawn')
            self.assertEqual(saved['fallback_intents'][0]['intent']['arguments'],{'action':'volume:down'})

    def test_api_errors_do_not_leak_key_or_retry(self):
        with patch('speech.openai_fallback.read_key',return_value='test-secret'), \
             patch('speech.openai_fallback.http.client.HTTPSConnection') as connection:
            connection.return_value.request.side_effect=RuntimeError('failed test-secret')
            result=openai_fallback.interpret('make it quieter',Grammar({}))
            connection.return_value.request.assert_called_once()
        self.assertEqual(result['status'],'error')
        self.assertNotIn('test-secret',json.dumps(result))

    def test_empty_transcript_never_calls_api(self):
        with patch('speech.openai_fallback.http.client.HTTPSConnection') as connection:
            with self.assertRaises(ValueError):openai_fallback.interpret('',Grammar({}))
        connection.assert_not_called()

    def test_raw_response_is_logged_before_invalid_body_is_rejected(self):
        for status,raw in [(500,'<html>failed</html>'),(200,'not json')]:
            self.audit.reset_mock()
            with patch('speech.openai_fallback.read_key',return_value='test-secret'), \
                 patch('speech.openai_fallback.http.client.HTTPSConnection') as connection:
                response=connection.return_value.getresponse.return_value
                response.status=status;response.read.return_value=raw.encode()
                response.getheader.return_value='req-test'
                result=openai_fallback.request_json({},'prompt',{},'observation')
            self.assertEqual(result['status'],'error')
            calls=self.audit.call_args_list
            self.assertEqual([c.args[0] for c in calls],['api_request','api_response','api_error'])
            self.assertEqual(calls[1].args[1]['raw_body'],raw)
            self.assertEqual(calls[1].args[1]['http_status'],status)
            self.assertEqual(calls[1].args[2],'observation')
