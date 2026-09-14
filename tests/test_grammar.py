"""Composition, semantic ambiguity, and compatibility of finite command grammars."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from command_catalog import EXPANSIONS, GRAMMAR, RULES, SCHEMAS, STRUCTURED_INTENTS, VOCABULARY
from grammar_engine import Word, compile_grammar
from intent_matching import IntentMatcher


class GrammarTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.matcher = IntentMatcher(Path(directory.name) / 'aliases.json')

    def test_shared_pattern_and_new_destination_expand_together(self):
        rule = replace(RULES[0], patterns=RULES[0].patterns + ('go to <destination>',))
        vocabulary = VOCABULARY | {'destination': VOCABULARY['destination'] + (
            Word('example', 'Example', ('example', 'example site')),)}
        schemas = SCHEMAS | {'open_destination': {'destination': ('gmail', 'github', 'example')}}
        expansions = compile_grammar((rule,), vocabulary, schemas)
        grammar = {e.phrase: e.command for e in expansions}
        meanings = {e.command: e.intent for e in expansions}
        with patch('intent_matching.GRAMMAR', grammar), patch('intent_matching.STRUCTURED_INTENTS', meanings):
            for name in ('gmail', 'github', 'example'):
                for prefix in ('open', 'bring up', 'go to'):
                    result = self.matcher.parse(f'{prefix} {name}')
                    self.assertEqual(result.intent.to_dict()['arguments'], {'destination': name})
                    fuzzy = self.matcher.parse(f'{prefix} {name}z')
                    self.assertEqual(fuzzy.method, 'fuzzy')
                    self.assertEqual(fuzzy.intent, result.intent)
        self.assertFalse(self.matcher.path.exists())

    def test_competing_slot_values_remain_ambiguous(self):
        vocabulary = {'destination': (Word('cat', 'Cat', ('cat',)), Word('bat', 'Bat', ('bat',)))}
        schemas = {'open_destination': {'destination': ('cat', 'bat')}}
        expansions = compile_grammar((RULES[0],), vocabulary, schemas)
        with patch('intent_matching.GRAMMAR', {e.phrase: e.command for e in expansions}), \
             patch('intent_matching.STRUCTURED_INTENTS', {e.command: e.intent for e in expansions}):
            result = self.matcher.parse('open hat')
            self.assertEqual(result.status, 'ambiguous')
            self.assertIsNone(result.intent)
            self.assertEqual(len(result.candidates), 2)

    def test_grammar_validation_rejects_collisions_and_invalid_bindings(self):
        rule = RULES[0]
        cases = [
            (rule, rule),
            (replace(rule, patterns=('open <missing>',)),),
            (replace(rule, patterns=('open <destination',)),),
            (replace(rule, arguments=(('destination', '$missing'),)),),
            (replace(rule, arguments=(('destination', 'unknown'),)),),
            (replace(rule, arguments=()),),
            (replace(rule, scope='browser'),),
            (rule, replace(rule, id='conflict', arguments=(('destination', 'github'),))),
        ]
        for rules in cases:
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                compile_grammar(rules, VOCABULARY, SCHEMAS)

    def test_structured_intents_preserve_target_and_presentation_distinctions(self):
        for first, second in [('close terminal', 'close this terminal'),
                              ('maximize chrome', 'maximize this window'),
                              ('open gmail', 'open github')]:
            self.assertNotEqual(self.matcher.parse(first).intent, self.matcher.parse(second).intent)
        self.assertEqual(self.matcher.parse('open chrome').intent, self.matcher.parse('bring up chrome').intent)
        self.assertEqual(self.matcher.parse('open g mail').intent, self.matcher.parse('bring up gmail').intent)

    def test_every_generated_phrase_parses_to_its_bound_meaning(self):
        for expansion in EXPANSIONS:
            parsed = self.matcher.parse(expansion.phrase.upper() + '!')
            self.assertEqual(parsed.intent, expansion.intent)
            self.assertEqual(parsed.command, expansion.command)
            evidence = parsed.selected.to_dict()['expansions']
            self.assertIn({'rule': expansion.rule_id, 'pattern': expansion.pattern,
                           'bindings': dict(expansion.bindings)}, evidence)

    def test_legacy_aliases_gain_structure_without_rewriting_or_learning(self):
        self.matcher.learn('open dis cord', 'discord')
        before = self.matcher.path.read_bytes()
        result = self.matcher.parse('open dis cord')
        self.assertEqual(result.method, 'alias')
        self.assertEqual(result.intent, STRUCTURED_INTENTS['discord'])
        self.matcher.parse('open git hubs')
        self.assertEqual(self.matcher.path.read_bytes(), before)

    def test_new_browser_expansions_share_existing_semantics(self):
        for prefix in ('open', 'launch', 'focus', 'switch to'):
            for name in ('chrome', 'chromium', 'google chrome'):
                self.assertEqual(GRAMMAR[f'{prefix} {name}'], 'browser')

    def test_focus_apps_reuses_open_intent_with_fuzzy_names(self):
        for name in ('discord', 'x', 'twitter'):
            expected = self.matcher.parse(f'open {name}').intent
            for prefix in ('focus', 'switch to'):
                with self.subTest(name=name, prefix=prefix):
                    result = self.matcher.parse(f'{prefix} {name}')
                    self.assertEqual(result.method, 'exact')
                    self.assertEqual(result.intent, expected)
        for phrase, app in [('focus discrod', 'discord'), ('switch to twiter', 'x')]:
            result = self.matcher.parse(phrase)
            self.assertEqual(result.method, 'fuzzy')
            self.assertEqual(result.intent, STRUCTURED_INTENTS[app])
