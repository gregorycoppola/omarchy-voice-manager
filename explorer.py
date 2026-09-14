"""Native, parse-only grammar explorer; independent of Skipper's voice runtime."""
import json
import os
from pathlib import Path
import sys
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from command_catalog import EXPANSIONS, INTENTS, RULES, SCHEMAS, STRUCTURED_INTENTS, VOCABULARY, WINDOW_RULES
from intent_matching import IntentMatcher
from settings import Settings
from window_vocabulary import live_windows, inject_windows


def label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0, wrap=True,
                       selectable=style not in {"title-1", "title-2", "title-3", "heading"})
    if style:
        widget.add_css_class(style)
    return widget


def column(spacing=12, margin=20):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, "set_margin_" + side)(margin)
    return box


def scroll(child):
    widget = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    widget.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    widget.set_child(child)
    return widget


def clear(box):
    while child := box.get_first_child():
        box.remove(child)


def intent_text(intent):
    arguments = ", ".join(f"{key}={value}" for key, value in intent.arguments)
    return f"{intent.type}({arguments})"


class CatalogPage(Gtk.Paned):
    """Searchable catalog with a readable detail pane."""
    def __init__(self, entries, render):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.entries = entries
        self.render = render
        self.set_position(290)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)
        sidebar = column(margin=12)
        self.search = Gtk.SearchEntry(placeholder_text="Filter…")
        self.search.connect("search-changed", self.filter_rows)
        sidebar.append(self.search)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.rows = []
        for title, subtitle, key, search_text in entries:
            row = Gtk.ListBoxRow()
            content = column(spacing=4, margin=10)
            content.append(label(title, "heading"))
            description = label(subtitle, "dim-label")
            description.set_selectable(False)
            content.append(description)
            row.set_child(content)
            row.key = key
            row.search_text = f"{title} {subtitle} {search_text}".lower()
            self.rows.append(row)
            self.list.append(row)
        self.list.connect("row-selected", self.selected)
        sidebar.append(scroll(self.list))
        self.set_start_child(sidebar)
        self.details = column()
        self.set_end_child(scroll(self.details))
        if self.rows:
            self.list.select_row(self.rows[0])

    def selected(self, _, row):
        clear(self.details)
        if row:
            self.render(self.details, row.key)
        else:
            self.details.append(label("No matching entries", "title-2"))

    def filter_rows(self, *_):
        query = self.search.get_text().strip().lower()
        for row in self.rows:
            row.set_visible(query in row.search_text)
        visible = [row for row in self.rows if row.get_visible()]
        current = self.list.get_selected_row()
        if current not in visible:
            self.list.select_row(visible[0] if visible else None)


def render_rule(box, rule, available=EXPANSIONS):
    expansions = [e for e in available if e.rule_id == rule.id]
    box.append(label(rule.id.replace('_', ' ').capitalize(), "title-1"))
    box.append(label(f"Scope: {rule.scope} · {len(expansions)} expansions · "
                     f"{len({e.intent for e in expansions})} meanings", "dim-label"))
    box.append(label("Patterns", "title-3"))
    box.append(label("\n".join(rule.patterns), "monospace"))
    box.append(label("Produces", "title-3"))
    template = f"{rule.intent_type}(" + ", ".join(f"{k}={v}" for k, v in rule.arguments) + ")"
    box.append(label(template, "monospace"))
    box.append(label("$name binds the canonical vocabulary ID.", "dim-label"))
    box.append(label("All expansions", "title-3"))
    for command in dict.fromkeys(e.command for e in expansions):
        group = [e for e in expansions if e.command == command]
        box.append(label(group[0].label, "heading"))
        box.append(label(intent_text(group[0].intent), "monospace"))
        box.append(label("\n".join(dict.fromkeys(e.phrase for e in group))))


def render_word(box, key):
    name, word = key
    box.append(label(word.label, "title-1"))
    box.append(label(f"<{name}> · canonical ID: {word.id}", "monospace"))
    box.append(label("Spoken forms", "title-3"))
    box.append(label("\n".join(word.forms)))
    expansions = [e for e in EXPANSIONS if (name, word.id) in e.bindings]
    box.append(label("Used by rules", "title-3"))
    box.append(label("\n".join(dict.fromkeys(e.rule_id for e in expansions)), "monospace"))
    box.append(label(f"{len(expansions)} expansions", "title-3"))
    box.append(label("\n".join(e.phrase for e in expansions)))


def render_schema(box, name):
    box.append(label(name, "title-1"))
    box.append(label("Typed arguments", "title-3"))
    box.append(label("\n".join(f"{key}: {' | '.join(values)}" for key, values in SCHEMAS[name].items())
                     or "No arguments", "monospace"))
    box.append(label("Registered meanings", "title-3"))
    for command, intent in STRUCTURED_INTENTS.items():
        if intent.type != name:
            continue
        box.append(label(INTENTS[command]['label'], "heading"))
        box.append(label(json.dumps(intent.to_dict(), indent=2), "monospace"))
        box.append(label(f"Execution ID: {command}", "dim-label"))
        box.append(label("\n".join(INTENTS[command]['phrases'])))


class Explorer(Gtk.Application):
    def __init__(self, alias_path=None):
        super().__init__(application_id="io.github.gregorycoppola.Skipper.Explorer",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option('tutorial', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Open the voice-command tutorial', None)
        self.add_main_option('history', 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             'Open command history and corrections', None)
        self.tutorial = None
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.alias_path = Path(alias_path) if alias_path else data / "skipper/aliases.json"
        self.window = None
        self.last_result = None
        self.player = None
        self.window_snapshot = inject_windows(None)
        self.windows_refreshing = False
        self.windows_timer = None
        self.connect('shutdown', self.stop_playback)

    def do_command_line(self, command_line):
        if command_line.get_options_dict().contains('tutorial'):
            self.show_tutorial()
        elif command_line.get_options_dict().contains('history'):
            self.show_history()
        else:
            self.activate()
        return 0

    def show_history(self, *_):
        self.activate()
        self.refresh_history()
        self.stack.set_visible_child_name('history')

    def show_tutorial(self, *_):
        if self.tutorial is None:
            from tutorial import TutorialWindow
            self.tutorial = TutorialWindow(self)
            self.tutorial.connect('close-request', self.tutorial_closed)
        self.tutorial.present()

    def tutorial_closed(self, *_):
        self.tutorial = None
        return False

    def explorer_closed(self, *_):
        self.stop_playback()
        self.window = None
        if self.windows_timer is not None:
            GLib.source_remove(self.windows_timer)
            self.windows_timer = None
        return False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title="Skipper Explorer")
        self.window.connect('close-request', self.explorer_closed)
        self.window.set_default_size(1040, 760)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Skipper Explorer"))
        tutorial = Gtk.Button(label='Tutorial')
        tutorial.connect('clicked', self.show_tutorial)
        header.pack_end(tutorial)
        history = Gtk.Button(label='History')
        history.connect('clicked', self.show_history)
        header.pack_end(history)
        self.window.set_titlebar(header)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        intro = column(spacing=6)
        intro.append(label("Explore the language", "title-1"))
        intro.append(label(f"{len(RULES) + len(WINDOW_RULES)} rules · fixed vocabulary + live window names", "dim-label"))
        root.append(intro)
        self.stack = Gtk.Stack(vexpand=True, hexpand=True)
        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        root.append(switcher)
        root.append(self.stack)
        self.rules_page = CatalogPage([
            (rule.id.replace('_', ' ').capitalize(), rule.patterns[0], rule,
             ' '.join(e.phrase for e in EXPANSIONS if e.rule_id == rule.id)) for rule in RULES + WINDOW_RULES
        ], lambda box, rule: render_rule(box, rule, EXPANSIONS + self.window_snapshot.expansions))
        self.stack.add_titled(self.rules_page, "rules", "Grammar")
        self.vocabulary_page = CatalogPage([
            (word.label, f"<{name}>", (name, word), ' '.join(word.forms))
            for name, words in VOCABULARY.items() for word in words
        ], render_word)
        self.stack.add_titled(self.vocabulary_page, "vocabulary", "Vocabulary")
        self.intents_page = CatalogPage([
            (name, f"{sum(i.type == name for i in STRUCTURED_INTENTS.values())} meanings", name,
             ' '.join(SCHEMAS[name])) for name in SCHEMAS
        ] + [(rule.intent_type, 'Live window binding', rule.intent_type, 'window terminal codex')
             for rule in WINDOW_RULES], self.render_intent_schema)
        self.stack.add_titled(self.intents_page, "intents", "Intents")
        playground = column()
        playground.append(label("Try a command", "title-1"))
        playground.append(label("See how words become an intent. Testing here does not run actions or learn phrases.", "dim-label"))
        line = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry(placeholder_text="Try “open g mail” or “open dis cord”", hexpand=True)
        self.entry.connect("activate", self.inspect)
        line.append(self.entry)
        inspect_button = Gtk.Button(label="Inspect")
        inspect_button.add_css_class("suggested-action")
        inspect_button.connect("clicked", self.inspect)
        line.append(inspect_button)
        playground.append(line)
        self.result_box = column(margin=0)
        self.result_box.append(label("Enter a phrase to inspect its meaning and matching evidence.", "dim-label"))
        playground.append(scroll(self.result_box))
        self.stack.add_titled(playground, "test", "Try a command")
        self.windows_box = column(margin=0)
        self.stack.add_titled(self.windows_box, 'windows', 'Live windows')
        self.windows_box.append(label('Reading live terminal names…', 'dim-label'))
        self.history_box = column(margin=0)
        self.stack.add_titled(self.history_box, "history", "History")
        self.refresh_history()
        self.preferences_box = column()
        self.stack.add_titled(scroll(self.preferences_box), "settings", "Settings & phrases")
        self.refresh_preferences()
        self.window.set_child(root)
        self.window.set_focus(self.rules_page.search)
        self.window.present()
        self.refresh_windows()
        self.windows_timer = GLib.timeout_add_seconds(2, self.refresh_windows)

    def refresh_windows(self):
        if self.windows_refreshing:
            return True
        self.windows_refreshing = True
        def read():
            try:
                GLib.idle_add(self.update_windows, live_windows(), None)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                GLib.idle_add(self.update_windows, inject_windows(None), str(exc))
        threading.Thread(target=read, daemon=True).start()
        return True

    def update_windows(self, snapshot, error):
        self.windows_refreshing = False
        if self.window is None:
            return
        previous = self.window_snapshot
        self.window_snapshot = snapshot
        if previous.revision == snapshot.revision and hasattr(self, 'windows_page') and not error:
            return
        selected = self.windows_page.list.get_selected_row() if hasattr(self, 'windows_page') else None
        selected_id = selected.key.id if selected else None
        query = self.windows_page.search.get_text() if hasattr(self, 'windows_page') else ''
        clear(self.windows_box)
        note = column(margin=12)
        note.append(label('Live <window> vocabulary', 'title-2'))
        note.append(label(error or 'Names refresh every two seconds. Voice commands use the window list captured when recording starts.', 'dim-label'))
        self.windows_box.append(note)
        self.windows_page = CatalogPage([
            (word.label, 'Terminal · ' + word.forms[0], word, ' '.join(word.forms)) for word in snapshot.words
        ], self.render_live_window)
        self.windows_box.append(self.windows_page)
        self.windows_page.set_vexpand(True)
        self.windows_page.search.set_text(query)
        self.windows_page.filter_rows()
        for row in self.windows_page.rows:
            if row.key.id == selected_id and row.get_visible():
                self.windows_page.list.select_row(row)
        if not snapshot.words:
            self.windows_page.details.append(label('No named terminal windows available.', 'dim-label'))
        row = self.rules_page.list.get_selected_row()
        if row and row.key in WINDOW_RULES:
            self.rules_page.selected(self.rules_page.list, row)

    def render_live_window(self, box, word):
        target = self.window_snapshot.targets[word.id]
        box.append(label(word.label, 'title-1'))
        box.append(label(f"{target['class']} · Workspace {target.get('workspace', {}).get('name', '?')}", 'dim-label'))
        box.append(label('Spoken names', 'title-3'))
        box.append(label('\n'.join(word.forms)))
        box.append(label('Grammar patterns', 'title-3'))
        box.append(label('\n'.join(pattern for rule in WINDOW_RULES for pattern in rule.patterns), 'monospace'))
        box.append(label('Generated phrases', 'title-3'))
        expansions = [e for e in self.window_snapshot.expansions if ('window', word.id) in e.bindings]
        box.append(label('\n'.join(e.phrase for e in expansions)))
        if expansions:
            box.append(label(json.dumps(expansions[0].intent.to_dict(), indent=2), 'monospace'))
        duplicates = [name for name in word.forms if sum(name in other.forms for other in self.window_snapshot.words) > 1]
        if duplicates:
            box.append(label('Shared names — use a more specific title: ' + ', '.join(duplicates), 'dim-label'))

    def render_intent_schema(self, box, name):
        if name not in {rule.intent_type for rule in WINDOW_RULES}:
            render_schema(box, name)
            return
        box.append(label(name, 'title-1'))
        box.append(label('window: an identity from the captured live <window> vocabulary', 'monospace'))
        if name == 'move_named_window':
            box.append(label('monitor: other (relative to the target window)', 'monospace'))
        if name == 'maximize_named_window':
            box.append(label('monitor: current (keep the target window on its screen)', 'monospace'))
        box.append(label('The same window keeps its identity when its title changes. Closed or replaced windows cannot be targeted by an old match.', 'dim-label'))
        for word in self.window_snapshot.words:
            box.append(label(word.label, 'heading'))
            box.append(label(name + '(window=' + word.id +
                             (', monitor=other' if name == 'move_named_window' else
                              ', monitor=current' if name == 'maximize_named_window' else '') + ')', 'monospace'))

    def stop_playback(self, *_):
        if self.player and self.player.poll() is None:
            self.player.terminate()

    def refresh_history(self, *_):
        clear(self.history_box)
        from diagnostics import LOG_PATH
        from history_ui import HistoryPage
        default_data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'skipper'
        log_path = LOG_PATH if self.alias_path.parent == default_data else self.alias_path.parent / 'commands.jsonl'
        self.history_page = HistoryPage(self, log_path)
        self.history_box.append(self.history_page)

    def render_recording(self, box, path):
        box.append(label(path.stem.replace('_', ' '), 'title-2'))
        try:
            text = path.with_suffix('.txt').read_text() if path.with_suffix('.txt').exists() else ''
        except OSError as exc:
            text = f'Could not read transcript: {exc}'
        box.append(label(text or 'Audio saved; no transcript yet.'))
        box.append(label('Saved transcript. Original intent history is not recorded yet.', 'dim-label'))
        buttons = Gtk.Box(spacing=8)
        feedback = label('', 'dim-label')
        for title, callback in (
            ('Play', lambda *_: self.play_recording(path, feedback)),
            ('Copy text', lambda *_: self.window.get_clipboard().set(text)),
            ('Transcribe again', lambda *_: self.retry_recording(path, feedback)),
            ('Open folder', lambda *_: Gio.AppInfo.launch_default_for_uri(path.parent.as_uri(), None)),
        ):
            button = Gtk.Button(label=title)
            button.connect('clicked', callback)
            buttons.append(button)
        box.append(buttons)
        box.append(feedback)

    def play_recording(self, path, feedback):
        self.stop_playback()
        try:
            self.player = subprocess.Popen(['pw-play', str(path)])
            feedback.set_text('Playing recording.')
        except OSError as exc:
            feedback.set_text(f'Could not play: {exc}')

    def retry_recording(self, path, feedback):
        try:
            result = subprocess.run(['gapplication', 'action', 'io.github.gregorycoppola.Skipper',
                                     'retry', GLib.Variant('s', path.stem).print_(False)],
                                    capture_output=True, text=True, timeout=3)
            feedback.set_text('Requested transcription. Skipper must be ready; refresh after it finishes.'
                              if result.returncode == 0 else 'Start Skipper from the bar, then retry.')
        except (OSError, subprocess.SubprocessError) as exc:
            feedback.set_text(f'Could not request transcription: {exc}')

    def refresh_preferences(self, *_):
        box = self.preferences_box
        clear(box)
        box.append(label('Voice settings', 'title-1'))
        settings = Settings(self.alias_path.parent / 'settings.json')
        feedback = label(settings.error or '', 'dim-label')
        toggle = Gtk.CheckButton(label='Confirm before closing a terminal with running programs')
        toggle.set_active(settings.confirm_terminal_close)
        def changed(button):
            try:
                settings.set_confirm_terminal_close(button.get_active())
                feedback.set_text('Saved. Applies to the next voice command.')
            except (OSError, ValueError) as exc:
                feedback.set_text(str(exc))
        toggle.connect('toggled', changed)
        toggle.set_sensitive(not bool(settings.error))
        box.append(toggle)
        box.append(feedback)
        box.append(label('Learned phrases', 'title-2'))
        refresh = Gtk.Button(label='Refresh phrases', halign=Gtk.Align.START)
        refresh.connect('clicked', self.refresh_preferences)
        box.append(refresh)
        matcher = IntentMatcher(self.alias_path)
        if matcher.error:
            box.append(label(matcher.error, 'error'))
        for phrase, command in sorted(matcher.aliases.items()):
            row = Gtk.Box(spacing=12)
            description = label(f'{phrase} → {INTENTS[command]["label"]}')
            description.set_hexpand(True)
            row.append(description)
            forget = Gtk.Button(label='Forget')
            forget.connect('clicked', self.forget_phrase, phrase)
            row.append(forget)
            box.append(row)
        if not matcher.aliases:
            box.append(label('Automatically learned phrases will appear here.', 'dim-label'))

    def forget_phrase(self, _, phrase):
        try:
            IntentMatcher(self.alias_path).forget(phrase)
            self.refresh_preferences()
        except (OSError, ValueError) as exc:
            self.preferences_box.append(label(str(exc), 'error'))

    def inspect(self, *_):
        # Reload aliases on each request so the live voice app's new phrases appear.
        matcher = IntentMatcher(self.alias_path)
        window_error = None
        try:
            snapshot = live_windows()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            snapshot = inject_windows(None)
            window_error = str(exc)
        result = matcher.parse(self.entry.get_text(), snapshot.expansions)
        self.last_result = result
        clear(self.result_box)
        box = self.result_box
        if matcher.error:
            box.append(label(matcher.error, "error"))
        if window_error:
            box.append(label('Live windows unavailable: ' + window_error, 'dim-label'))
        box.append(label(result.status.capitalize(), "title-2"))
        if result.selected:
            box.append(label(result.selected.label, "title-3"))
            box.append(label(json.dumps(result.intent.to_dict(), indent=2), "monospace"))
            box.append(label(f"Match: {result.method} · Heard as: {result.selected.phrase}", "dim-label"))
        if result.reason:
            box.append(label(result.reason))
        if result.candidates:
            box.append(label("Matching evidence", "title-3"))
            box.append(label("Similarity is a text score, not a confidence probability. "
                             "Fuzzy matches need at least 0.72 and a 0.06 lead over a different meaning.", "dim-label"))
        for candidate in result.candidates:
            box.append(label(f"{candidate.score:.3f} · {candidate.phrase}", "heading"))
            box.append(label(intent_text(candidate.intent), "monospace"))
            evidence = candidate.to_dict()
            rules = ', '.join(evidence['rules'])
            box.append(label(f"Source: {candidate.source}" + (f" · Rule: {rules}" if rules else ''), "dim-label"))
            for expansion in evidence['expansions']:
                bindings = ', '.join(f"{key}={value}" for key, value in expansion['bindings'].items())
                box.append(label(expansion['pattern'] + (f" → {bindings}" if bindings else ''), "monospace"))


if __name__ == "__main__":
    raise SystemExit(Explorer().run(sys.argv))
