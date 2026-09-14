"""Save, apply, edit and remove a correction through the real GTK controls."""
from pathlib import Path
import json
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from explorer import Explorer
from intent_matching import IntentMatcher
from corrections import Corrections
from gi.repository import GLib

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    recordings = root / 'recordings'
    recordings.mkdir()
    audio = recordings / 'example.wav'
    audio.touch()
    audio.with_suffix('.txt').write_text('Tile the app.')
    (root / 'commands.jsonl').write_text(json.dumps(dict(event='parsed', recording=str(audio),
        command=None, result=dict(text='Tile the app.', status='unrecognized', method=None))) + '\n')
    app = Explorer(root / 'aliases.json')
    app.set_application_id('io.github.gregorycoppola.Skipper.HistoryTest')
    errors = []

    def check():
        try:
            assert app.stack.get_visible_child_name() == 'history'
            page = app.history_page
            row = page.rows[0]
            row.meant.set_text('tile all apps')
            row.choice.set_selected(page.commands.index('apps:tile') + 1)
            row.save.emit('clicked')
            matcher = IntentMatcher(root / 'aliases.json')
            assert matcher.parse('Tile the app!').method == 'correction'
            assert matcher.parse('Tile the app!').command == 'apps:tile'
            page.refresh()
            row = page.rows[0]
            assert row.meant.get_text() == 'tile all apps'
            row.meant.set_text('hide all apps')
            row.choice.set_selected(page.commands.index('apps:hide') + 1)
            row.save.emit('clicked')
            assert matcher.parse('Tile the app!').command == 'apps:hide'
            row.remove.emit('clicked')
            assert matcher.parse('Tile the app!').method == 'fuzzy'
            assert len(Corrections(root / 'corrections.json').events) == 3
            assert audio.with_suffix('.txt').read_text() == 'Tile the app.'
            assert 'os_actions' not in sys.modules and 'onnxruntime' not in sys.modules
            print('PASS: direct History launch, correction save/apply/edit/remove, original transcript retained, no action/model imports')
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            app.quit()
        return False

    GLib.timeout_add(500, check)
    app.run(['history-test', '--history'])
    assert not errors, errors
