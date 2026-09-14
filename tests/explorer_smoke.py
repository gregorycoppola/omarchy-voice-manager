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
    app.set_application_id('io.github.gregorycoppola.Keety.ExplorerTest')
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
            assert 'gui' not in sys.modules
            assert 'os_actions' not in sys.modules
            assert 'keety' not in sys.modules
            passed.append(True)
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            app.quit()
        return False

    GLib.timeout_add(300, test)
    app.run(['explorer-smoke'])
    assert passed and not errors, errors
    print('PASS: native catalog browsing/filtering, exact/fuzzy/alias inspection, no runtime imports')
