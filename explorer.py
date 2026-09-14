"""Native, parse-only grammar explorer; independent of Keety's voice runtime."""
import json
import os
from pathlib import Path
import sys

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from command_catalog import EXPANSIONS, INTENTS, RULES, SCHEMAS, STRUCTURED_INTENTS, VOCABULARY
from intent_matching import IntentMatcher


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


def render_rule(box, rule):
    expansions = [e for e in EXPANSIONS if e.rule_id == rule.id]
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
        super().__init__(application_id="io.github.gregorycoppola.Keety.Explorer")
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.alias_path = Path(alias_path) if alias_path else data / "keety/aliases.json"
        self.window = None
        self.last_result = None

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title="Keety Explorer")
        self.window.set_default_size(1040, 760)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Keety Explorer"))
        self.window.set_titlebar(header)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        intro = column(spacing=6)
        intro.append(label("Explore the language", "title-1"))
        intro.append(label(f"{len(RULES)} rules · {len(SCHEMAS)} intent types · "
                           f"{len(STRUCTURED_INTENTS)} meanings · {len(EXPANSIONS)} expansions", "dim-label"))
        root.append(intro)
        self.stack = Gtk.Stack(vexpand=True, hexpand=True)
        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        root.append(switcher)
        root.append(self.stack)
        self.rules_page = CatalogPage([
            (rule.id.replace('_', ' ').capitalize(), rule.patterns[0], rule,
             ' '.join(e.phrase for e in EXPANSIONS if e.rule_id == rule.id)) for rule in RULES
        ], render_rule)
        self.stack.add_titled(self.rules_page, "rules", "Grammar")
        self.vocabulary_page = CatalogPage([
            (word.label, f"<{name}>", (name, word), ' '.join(word.forms))
            for name, words in VOCABULARY.items() for word in words
        ], render_word)
        self.stack.add_titled(self.vocabulary_page, "vocabulary", "Vocabulary")
        self.intents_page = CatalogPage([
            (name, f"{sum(i.type == name for i in STRUCTURED_INTENTS.values())} meanings", name,
             ' '.join(SCHEMAS[name])) for name in SCHEMAS
        ], render_schema)
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
        self.window.set_child(root)
        self.window.set_focus(self.rules_page.search)
        self.window.present()

    def inspect(self, *_):
        # Reload aliases on each request so the live voice app's new phrases appear.
        matcher = IntentMatcher(self.alias_path)
        result = matcher.parse(self.entry.get_text())
        self.last_result = result
        clear(self.result_box)
        box = self.result_box
        if matcher.error:
            box.append(label(matcher.error, "error"))
        box.append(label(result.status.capitalize(), "title-2"))
        if result.selected:
            box.append(label(INTENTS[result.command]['label'], "title-3"))
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
