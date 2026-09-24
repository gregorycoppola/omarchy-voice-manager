"""Named-action editor. Saving previews a meaning without executing it."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from command_catalog import INTENTS
from custom_actions import CustomActions, COMMANDS


class ActionsPage(Gtk.Box):
    def __init__(self, path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
        self.path = path
        self.editing = None
        self.commands = sorted(COMMANDS, key=lambda c: INTENTS[c]['label'])
        self.append(Gtk.Label(label='Named actions', xalign=0))
        self.append(Gtk.Label(label='Give a supported action your own exact phrase. Saving does not run it.\n'
                              'Window choices and terminal-close confirmations still apply.', xalign=0, wrap=True))
        self.name = Gtk.Entry(placeholder_text='Name, e.g. Quiet time')
        self.phrase = Gtk.Entry(placeholder_text='Phrase, e.g. make it quiet')
        self.choice = Gtk.DropDown.new_from_strings([INTENTS[c]['label'] for c in self.commands])
        self.preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.choice.connect('notify::selected', self.update_preview)
        for widget in (self.name, self.phrase, self.choice, self.preview):
            self.append(widget)
        buttons = Gtk.Box(spacing=8)
        for title, callback in [('Save action', self.save), ('New / cancel edit', self.reset), ('Refresh', self.refresh)]:
            button = Gtk.Button(label=title)
            button.connect('clicked', callback)
            buttons.append(button)
        self.append(buttons)
        self.feedback = Gtk.Label(xalign=0, wrap=True)
        self.append(self.feedback)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(self.rows)
        self.update_preview()
        self.refresh()

    def update_preview(self, *_):
        command = self.commands[self.choice.get_selected()]
        self.preview.set_text('Action: ' + INTENTS[command]['label'] + '\nBuilt-in wording: ' + INTENTS[command]['phrases'][0])

    def reset(self, *_):
        self.editing = None
        self.name.set_text('')
        self.phrase.set_text('')
        self.feedback.set_text('New action. Choose its meaning above.')

    def save(self, *_):
        try:
            store = CustomActions(self.path)
            store.save(self.name.get_text(), self.phrase.get_text(),
                       self.commands[self.choice.get_selected()], self.editing)
            self.reset()
            self.refresh()
            self.feedback.set_text('Saved. Available immediately in speech and typed commands.')
        except (OSError, ValueError, TypeError) as exc:
            self.feedback.set_text(str(exc))

    def edit(self, key, action):
        self.editing = key
        self.name.set_text(action['name'])
        self.phrase.set_text(action['phrase'])
        self.choice.set_selected(self.commands.index(action['command']))
        self.feedback.set_text('Editing ' + action['name'])

    def remove(self, key):
        try:
            CustomActions(self.path).remove(key)
            if self.editing == key:
                self.reset()
            self.refresh()
            self.feedback.set_text('Action removed.')
        except (OSError, ValueError) as exc:
            self.feedback.set_text(str(exc))

    def refresh(self, *_):
        while child := self.rows.get_first_child():
            self.rows.remove(child)
        store = CustomActions(self.path)
        self.feedback.set_text(store.error or '')
        for key, action in store.actions.items():
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=f"{action['name']}: {action['phrase']} → {INTENTS[action['command']]['label']}",
                                 xalign=0, wrap=True, hexpand=True))
            edit = Gtk.Button(label='Edit')
            edit.connect('clicked', lambda _, k=key, a=action: self.edit(k, a))
            row.append(edit)
            remove = Gtk.Button(label='Remove')
            remove.connect('clicked', lambda _, k=key: self.remove(k))
            row.append(remove)
            self.rows.append(row)
