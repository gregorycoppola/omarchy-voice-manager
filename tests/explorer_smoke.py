"""Exercise the native explorer without speech, actions, or user-data writes."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer import Explorer
from gi.repository import GLib

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'aliases.json'
    app = Explorer(path)
    app.set_application_id('io.github.gregorycoppola.Skipper.ExplorerTest')
    errors = []
    passed = []

    def test():
        try:
            assert app.window.get_visible()
            for name, page in [('rules', app.rules_page), ('vocabulary', app.vocabulary_page),
                               ('intents', app.intents_page)]:
                app.stack.set_visible_child_name(name)
                for row in page.rows:
                    page.list.select_row(row)
                    assert page.details.get_first_child() is not None
                page.search.set_text('no possible match')
                page.filter_rows()
                assert not any(row.get_visible() for row in page.rows)
                page.search.set_text('')
                page.filter_rows()
                assert all(row.get_visible() for row in page.rows)
            app.stack.set_visible_child_name('test')
            for text, status, method in [('open g mail', 'matched', 'exact'),
                                         ('open dis cord', 'matched', 'fuzzy'),
                                         ("don't open chrome", 'unrecognized', None)]:
                app.entry.set_text(text)
                app.entry.emit('activate')
                assert app.last_result.status == status
                assert app.last_result.method == method
            path.write_text('{"version":1,"aliases":{"my mail":"site:gmail"}}')
            app.entry.set_text('my mail')
            app.inspect()
            assert app.last_result.method == 'alias'
            assert dict(app.last_result.intent.arguments) == {'destination': 'gmail'}
            assert len(list(Path(directory).iterdir())) == 1
            recordings = Path(directory) / 'recordings'
            recordings.mkdir()
            (recordings / 'example.wav').touch()
            (recordings / 'example.txt').write_text('Open Gmail.')
            app.refresh_history()
            app.stack.set_visible_child_name('history')
            assert len(app.history_page.rows) == 1
            assert app.history_page.rows[0].heard == 'Open Gmail.'
            app.stack.set_visible_child_name('settings')
            app.refresh_preferences()
            toggle = app.preferences_box.get_first_child().get_next_sibling()
            toggle.set_active(False)
            from settings import Settings
            assert Settings(Path(directory) / 'settings.json').confirm_terminal_close is False
            app.forget_phrase(None, 'my mail')
            from intent_matching import IntentMatcher
            assert not IntentMatcher(path).aliases
            from window_vocabulary import inject_windows
            from unittest.mock import patch
            context = {'clients': [{'class': 'foot', 'address': '0x123', 'pid': 123,
                                     'stableId': 'test-window', 'title': 'Test task | demo'}]}
            snapshot = inject_windows(context)
            app.update_windows(snapshot, None)
            app.stack.set_visible_child_name('windows')
            assert len(app.windows_page.rows) == 1
            with patch('explorer.live_windows', return_value=snapshot):
                app.entry.set_text('focus demo terminal')
                app.inspect()
            assert app.last_result.intent.type == 'focus_window'
            context['clients'][0]['title'] = 'Changed task | demo'
            app.update_windows(inject_windows(context), None)
            assert app.windows_page.rows[0].key.label == 'Changed task | demo'
            app.update_windows(inject_windows(None), None)
            assert not app.windows_page.rows
            assert 'gui' not in sys.modules
            assert 'os_actions' not in sys.modules
            assert 'skipper' not in sys.modules
            passed.append(True)
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            app.quit()
        return False

    GLib.timeout_add(300, test)
    app.run(['explorer-smoke'])
    assert passed and not errors, errors
    print('PASS: catalog/parse inspection, live window refresh, history, settings, phrase removal, no action imports')
