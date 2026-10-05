"""Unknown-command correction lifecycle and three-layer persistence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from corrections import Corrections
from intent_matching import IntentMatcher
from runtime import VoiceRuntime


class UnknownCorrectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = VoiceRuntime(self.root, self.root / 'status.json')
        for context in [patch.object(self.app, 'show_correction'),
                        patch('runtime.GLib.idle_add', side_effect=lambda fn, *a: fn(*a))]:
            context.start()
            self.addCleanup(context.stop)

    def unknown(self, text='towel these with internet'):
        with patch.object(self.app, 'execute') as execute:
            self.app.interpret(text, {}, commands=True, source='speech')
        execute.assert_not_called()
        return self.app.state['correction']['token']

    def request(self, token, operation='preview', said='tile this with internet', meant='tile this window and the browser'):
        self.app.correct_command(json.dumps(dict(token=token, operation=operation, said=said, meant=meant)))

    def test_unknown_opens_prompt_and_saves_three_layers_without_running(self):
        token = self.unknown()
        self.assertEqual(self.app.state['state'], 'Correction')
        self.assertIn('towel these with internet', self.app.state['message'])
        self.app.show_correction.assert_called_once()
        with patch.object(self.app, 'execute') as execute:
            self.request(token)
            self.assertEqual(self.app.state['correction']['preview']['intent']['type'], 'tile_current_window_with_browser')
            self.request(token, 'save')
        execute.assert_not_called()
        store = Corrections(self.root / 'corrections.json')
        rule = store.rules['towel these with internet']
        self.assertEqual((rule['heard'], rule['said'], rule['meant']),
                         ('towel these with internet', 'tile this with internet', 'tile this window and the browser'))
        result = IntentMatcher(self.root / 'aliases.json').parse('Towel these with internet!')
        self.assertEqual(result.method, 'correction')
        self.assertEqual(dict(result.intent.arguments)['second'], 'the browser')
        self.assertIsNone(self.app.pending_correction)
        self.assertFalse((self.root / 'aliases.json').exists())

    def test_recognized_commands_never_request_word_correction(self):
        for text in ('open chrome', 'open dis cord'):
            with patch.object(self.app, 'execute', return_value='Done') as execute, \
                 patch.object(self.app, 'offer_correction') as offer:
                self.app.interpret(text, {}, commands=True, source='speech')
            execute.assert_called_once()
            offer.assert_not_called()

    def test_preview_required_and_changed_words_cannot_save_old_meaning(self):
        token = self.unknown()
        self.request(token, 'save')
        self.assertIn('Check', self.app.state['correction']['error'])
        self.request(token)
        self.request(token, 'save', meant='hide all apps')
        self.assertFalse((self.root / 'corrections.json').exists())

    def test_unknown_typed_words_remain_editable_and_do_not_save(self):
        token = self.unknown()
        self.request(token, meant='purple asparagus dances briskly')
        self.assertIsNone(self.app.state['correction']['preview'])
        self.assertTrue(self.app.state['correction']['error'])
        self.assertEqual(self.app.state['state'], 'Correction')

    def test_cancel_and_old_tokens_do_not_affect_new_prompt(self):
        old = self.unknown()
        self.app.cancel(old)
        new = self.unknown('violet waterfalls spin')
        self.request(old)
        self.app.cancel(old)
        self.assertEqual(self.app.pending_correction['token'], new)
        self.assertIsNone(self.app.state['correction']['preview'])
        self.app.cancel(new)
        self.assertFalse((self.root / 'corrections.json').exists())

    def test_same_spoken_words_can_express_meaning_and_old_rules_still_work(self):
        token = self.unknown()
        self.request(token, said='tile the apps', meant='')
        self.request(token, 'save', said='tile the apps', meant='')
        matcher = IntentMatcher(self.root / 'aliases.json')
        self.assertEqual(matcher.parse('towel these with internet').command, 'apps:tile')
        store = Corrections(self.root / 'corrections.json')
        store.save('another phrase', 'open chrome', 'browser')
        self.assertEqual(matcher.parse('another phrase').command, 'browser')
        self.assertEqual(matcher.parse('towel these with internet').command, 'apps:tile')

    def test_corrections_do_not_chain_or_retain_old_window_ids(self):
        matcher = IntentMatcher(self.root / 'aliases.json')
        result = matcher.parse('tile this window and the browser', use_corrections=False)
        store = Corrections(self.root / 'corrections.json')
        store.save_wording('odd words', 'tile this and browser', 'tile this window and the browser', result)
        store.save('tile this window and the browser', 'hide all apps', 'apps:hide')
        self.assertEqual(matcher.parse('odd words').intent.type, 'tile_current_window_with_browser')
        self.assertNotIn('address', json.dumps(store.rules['odd words']))


if __name__ == '__main__':
    unittest.main()
