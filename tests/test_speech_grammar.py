import tempfile
from pathlib import Path
import unittest
from command_catalog import EXPANSIONS
from installed_apps import discover_installed_apps
from grammar_engine import Word
from speech.grammar import Grammar


class SpeechGrammarTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        (root/'chromium.desktop').write_text('[Desktop Entry]\nType=Application\nName=Chromium\nExec=true\n')
        (root/'alpha.desktop').write_text('[Desktop Entry]\nType=Application\nName=Project Alpha\nExec=true\n')
        self.g=Grammar({'active':{'workspace':{'id':7}}},discover_installed_apps(roots=(root,),for_picker=True))

    def test_every_authored_phrase_preserves_its_meaning(self):
        grammar=Grammar()
        for expansion in EXPANSIONS:
            with self.subTest(phrase=expansion.phrase):
                candidates=grammar.parse(expansion.phrase)['candidates']
                self.assertIn(expansion.intent.canonical_plan(),[c.get('canonical_plan') for c in candidates])

    def test_default_and_explicit_workspace(self):
        for phrase,workspace,source in [('open chromium','current','default'),('start chromium in the current workspace','current','explicit'),('launch chromium in workspace three','3','explicit')]:
            result=self.g.parse(phrase);self.assertEqual(result['status'],'matched')
            candidate=result['candidates'][0]
            self.assertEqual(candidate['launch_options']['workspace'],workspace)
            self.assertEqual(candidate['argument_sources']['workspace'],source)
            self.assertEqual(candidate['resolved_workspace'],7 if workspace=='current' else 3)

    def test_multiword_slot_followed_by_more_words(self):
        r=self.g.parse('open project alpha in workspace nineteen and tile it')
        self.assertEqual(r['status'],'matched')
        c=r['candidates'][0]
        self.assertEqual(c['bindings']['installed_app'],'alpha')
        self.assertEqual(c['launch_options'],{'workspace':'19','tile':True})

    def test_no_fuzzy_no_partial_or_invalid_defaults(self):
        for phrase in ['open chrome yum','do not open chromium','open chromium in workspace banana',
                       'open chromium in workspace zero','open chromium in workspace -1',
                       'open chromium and shut down','open chromium in workspace three nonsense']:
            self.assertEqual(self.g.parse(phrase)['status'],'unrecognized',phrase)

    def test_spoken_numbers(self):
        r=self.g.parse('switch to workspace nineteen')
        self.assertEqual(r['candidates'][0]['canonical_plan'][0]['arguments']['workspace'],19)

    def test_competing_entities_remain_ambiguous(self):
        self.g.lexicon['installed_app'].append((['chromium'],'other-app'))
        self.assertEqual(self.g.parse('open chromium')['status'],'ambiguous')

    def test_interactive_request_is_not_complete_action(self):
        self.assertEqual(self.g.parse('focus a tab')['status'],'needs_selection')
        self.assertEqual(self.g.parse('open file')['status'],'needs_selection')

    def test_multiword_named_window(self):
        from types import SimpleNamespace
        windows=SimpleNamespace(words=(Word('window-id','Project alpha',('project alpha terminal',)),))
        grammar=Grammar(windows=windows)
        r=grammar.parse('move project alpha terminal to workspace three')
        self.assertEqual(r['status'],'matched')
        self.assertEqual(r['candidates'][0]['bindings'],{'window':'window-id','number':'3'})

    def test_explicit_new_tab_preserves_new_tab_semantics(self):
        grammar=Grammar()
        for phrase in ('open github in a new tab','open git hub in another tab',
                       'launch gmail in a new tab','open a new tab for github'):
            result=grammar.parse(phrase)
            self.assertEqual(result['status'],'matched',phrase)
            self.assertTrue(result['candidates'][0]['command'].startswith('site-new:'))
        self.assertEqual(grammar.parse('open github')['candidates'][0]['command'],'site:github')
        self.assertEqual(grammar.parse('open github in a new tab tomorrow')['status'],'unrecognized')
