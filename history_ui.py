"""Three-column correction editor; saving never executes an action."""
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from command_catalog import INTENTS, STRUCTURED_INTENTS
from command_history import recent_recordings
from corrections import Corrections
from grammar_engine import normalize
from intent_matching import IntentMatcher


def label(text, style=None):
    widget = Gtk.Label(label=text, wrap=True, xalign=0, selectable=style not in ('title-2', 'heading'))
    widget.set_max_width_chars(38)
    if style:
        widget.add_css_class(style)
    return widget


def column():
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)


class HistoryPage(Gtk.Box):
    def __init__(self, app, log_path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.app, self.log_path = app, log_path
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(self, 'set_margin_' + side)(16)
        self.commands = sorted(INTENTS, key=lambda command: INTENTS[command]['label'])
        self.command_labels = ['Choose an action…'] + [INTENTS[command]['label'] for command in self.commands]
        self.append(label('Correct what Skipper understood', 'title-2'))
        self.append(label('Edit the words, choose the action, then Save correction. The same heard phrase will use your choice next time '
                          '(ignoring case and punctuation). Saving does not run it. Remove correction restores normal matching.'))
        toolbar = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text='Search recent recordings…', hexpand=True)
        self.search.connect('search-changed', self.filter_rows)
        toolbar.append(self.search)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', self.refresh)
        toolbar.append(refresh)
        self.append(toolbar)
        headings = Gtk.Box(spacing=20, homogeneous=True)
        for title in ('1. What was heard', '2. Words you meant', '3. Intended action'):
            headings.append(label(title, 'heading'))
        self.append(headings)
        self.body = column()
        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.body)
        self.append(scroller)
        self.refresh()

    def refresh(self, *_):
        while child := self.body.get_first_child():
            self.body.remove(child)
        self.rows = []
        store = Corrections(self.app.alias_path.with_name('corrections.json'))
        if store.error:
            self.body.append(label(store.error, 'error'))
        try:
            records = recent_recordings(self.app.alias_path.parent / 'recordings', self.log_path)
        except OSError as exc:
            self.body.append(label(f'Could not read history: {exc}', 'error'))
            return
        seen = {normalize(record['heard']) for record in records}
        for phrase, rule in store.rules.items():
            if phrase not in seen:
                records.append(dict(recording=rule.get('recording') or '', heard=rule.get('heard', phrase),
                                    parsed=None, outcome='Saved correction', timestamp=rule.get('updated_at', '')))
        for record in records:
            self.add_record(record, store)
        if not records:
            self.body.append(label('No recordings yet. Speak a command, then click Refresh.'))
        self.filter_rows()

    def add_record(self, record, store):
        heard = record['heard'].strip()
        saved = store.rules.get(normalize(heard))
        row = column()
        cells = Gtk.Box(spacing=20, homogeneous=True)
        first, second, third = column(), column(), column()
        for cell in (first, second, third):
            cells.append(cell)
        first.append(label(heard or 'No transcript available', 'heading'))
        first.append(label(record['timestamp'], 'dim-label'))
        feedback = label('', 'dim-label')
        play = Gtk.Button(label='Play recording', halign=Gtk.Align.START)
        play.set_sensitive(Path(record['recording']).is_file())
        play.connect('clicked', lambda *_: self.app.play_recording(Path(record['recording']), feedback))
        first.append(play)
        retry = Gtk.Button(label='Transcribe again', halign=Gtk.Align.START)
        retry.set_sensitive(Path(record['recording']).is_file())
        retry.connect('clicked', lambda *_: self.app.retry_recording(Path(record['recording']), feedback))
        first.append(retry)
        meant = Gtk.Entry(text=saved['meant'] if saved else heard, hexpand=True)
        second.append(meant)
        find = Gtk.Button(label='Match these words', halign=Gtk.Align.START)
        second.append(find)
        model = Gtk.StringList.new(self.command_labels)
        choice = Gtk.DropDown(model=model, enable_search=True, hexpand=True)
        expression = Gtk.PropertyExpression.new(Gtk.StringObject, None, 'string')
        choice.set_expression(expression)
        command = saved['command'] if saved else record.get('command')
        choice.set_selected(self.commands.index(command) + 1 if command in self.commands else 0)
        third.append(choice)
        parsed = record['parsed']
        if parsed:
            original = INTENTS.get(record.get('command'), {}).get('label')
            if not original and parsed.get('intent'):
                original = str(parsed['intent'])
            third.append(label('Originally: ' + (original or parsed.get('status', 'Unknown')) +
                               (' · ' + parsed['method'] if parsed.get('method') else ''), 'dim-label'))
        else:
            third.append(label('Original intent was not logged.', 'dim-label'))
        if record['outcome']:
            third.append(label(record['outcome'], 'dim-label'))
        buttons = Gtk.Box(spacing=8)
        save = Gtk.Button(label='Save correction')
        save.add_css_class('suggested-action')
        save.set_sensitive(bool(heard) and not store.error)
        remove = Gtk.Button(label='Remove correction')
        remove.set_sensitive(bool(saved) and not store.error)
        buttons.append(save)
        buttons.append(remove)
        row.append(cells)
        row.append(buttons)
        row.append(feedback)
        row.append(Gtk.Separator())
        if saved:
            feedback.set_text('Saved correction applies to this exact heard phrase.')

        def match_words(*_):
            result = IntentMatcher(self.app.alias_path).parse(meant.get_text())
            if result.command in self.commands:
                choice.set_selected(self.commands.index(result.command) + 1)
                feedback.set_text('Suggested action selected. Check it, then Save correction.')
            else:
                choice.set_selected(0)
                feedback.set_text('No clear action. Choose the intended action from the list.')

        def save_rule(*_):
            try:
                index = choice.get_selected()
                if not 1 <= index <= len(self.commands):
                    raise ValueError('Choose an intended action first.')
                Corrections(self.app.alias_path.with_name('corrections.json')).save(
                    heard, meant.get_text(), self.commands[index - 1], record['recording'])
                feedback.set_text('Saved. The next time Skipper hears this phrase, it will use your chosen action.')
                remove.set_sensitive(True)
            except (OSError, ValueError) as exc:
                feedback.set_text(str(exc))

        def remove_rule(*_):
            try:
                Corrections(self.app.alias_path.with_name('corrections.json')).forget(heard)
                feedback.set_text('Removed. Normal matching is restored for this phrase.')
                remove.set_sensitive(False)
            except (OSError, ValueError) as exc:
                feedback.set_text(str(exc))

        find.connect('clicked', match_words)
        save.connect('clicked', save_rule)
        remove.connect('clicked', remove_rule)
        row.heard, row.meant, row.choice, row.save, row.remove = heard, meant, choice, save, remove
        row.search_text = (heard + ' ' + record['timestamp']).lower()
        self.rows.append(row)
        self.body.append(row)

    def filter_rows(self, *_):
        query = self.search.get_text().lower().strip()
        for row in getattr(self, 'rows', []):
            row.set_visible(query in row.search_text or query in row.meant.get_text().lower())
