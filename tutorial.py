"""A lightweight, read-only introduction to Skipper's voice commands."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

# Canonical spoken examples are checked against the command catalog in tests.
LESSONS = (
    ('Start here', 'Speak, release, and check the result',
     'Start Skipper from its taskbar dropdown and wait for Ready. With the default shortcut installed, '
     'hold Super (Command) + R, say one command, then release. Skipper transcribes after you release. '
     'The dropdown shows what it heard and the action it chose.',
     (('show all windows', 'Open a window picker. Select a window to bring it forward.'),),
     'To try a command, focus the app you want to work with first. Reading this tutorial does not run any commands.'),
    ('Arrange windows', 'Choose what you want to see',
     'Tiling uses the workspace focused when you start speaking. You can switch views repeatedly; '
     'Skipper remembers windows hidden by an earlier view on that workspace.',
     (('tile all terminals', 'Tile terminals and hide other apps.'),
      ('tile all browsers', 'Tile browser windows and hide everything else.'),
      ('tile all apps', 'Tile non-terminal apps and hide terminals.'),
      ('tile all windows', 'Bring hidden windows back and tile everything together.')),
     '“Apps” means everything except terminals. Say “tile all apps” or “tile the apps” exactly. Other workspaces are left alone.'),
    ('Hide and restore', 'Put windows away without closing them',
     'Hide commands put windows out of view while their programs keep running. They do not run the tiling step '
     'or restore windows you already hid.',
     (('hide this window', 'Hide the window focused when you start speaking.'),
      ('hide all terminals', 'Hide terminals on that workspace.'),
      ('hide all apps', 'Hide non-terminal apps on that workspace.'),
      ('tile all windows', 'Restore hidden windows and arrange them in a grid.')),
     'Use these hide phrases exactly. Focus another app before saying “hide this window”, or you will hide this tutorial.'),
    ('Open and move', 'Bring an app into view',
     'Supported apps must already be installed. Window commands work locally; opening a website may need '
     'network access. Gmail and GitHub tab commands also need the optional browser connection.',
     (('open a new terminal', 'Open a fresh terminal window.'),
      ('open chrome', 'Open or bring forward Chrome / Chromium.'),
      ('open discord', 'Open or bring forward Discord.'),
      ('maximize this window', 'Maximize the window you were using.'),
      ('move this window to the other screen', 'Move that window to another connected screen.')),
     '“This window” is captured when recording starts. Moving to another screen requires at least two screens.'),
    ('Terminal names', 'Pick a terminal by its title',
     'Skipper uses terminal titles and project names to identify windows. For a terminal whose title contains '
     '“My project”, you can say “focus my project”, “maximize my project”, or '
     '“move my project to the other screen”. These are examples: use a name from your own terminal titles.',
     (),
     'If several terminals share a project name, use a more specific task title. Explorer’s Live windows page '
     'shows the names Skipper currently recognizes.'),
    ('Close and troubleshoot', 'Check the target before closing',
     'Closing can stop programs in a terminal. Skipper asks for confirmation when it detects running programs '
     'or cannot determine their state, unless you turned that preference off.',
     (('close this terminal', 'Close the terminal focused when you start speaking.'),
      ('close terminal', 'Close the most recently used terminal across workspaces.'),
      ('close chrome', 'Ask a Chrome / Chromium window to close.')),
     'If a command goes wrong, check the recognized words in the dropdown. Use Explorer to inspect commands, '
     'recording history, and learned phrases. Say one command at a time. Quit in the dropdown stops Skipper’s '
     'background process; closing this tutorial does not.'),
)


def text_label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0, wrap=True,
                       selectable=style not in {'title-1', 'title-2', 'heading'})
    widget.set_max_width_chars(68)
    if style:
        widget.add_css_class(style)
    return widget


class TutorialWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Skipper Tutorial')
        self.set_default_size(820, 650)
        self.index = 0
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label='Skipper Tutorial'))
        commands = Gtk.Button(label='All commands')
        commands.connect('clicked', lambda *_: app.activate())
        header.pack_end(commands)
        self.set_titlebar(header)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, 'set_margin_' + side)(20)
        root.append(text_label('Your desktop, by voice', 'title-1'))
        root.append(text_label('A quick guide to speaking with Skipper.', 'dim-label'))
        self.stack = Gtk.Stack(vexpand=True, hexpand=True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, vexpand=True)
        sidebar = Gtk.StackSidebar(stack=self.stack)
        body.append(sidebar)
        body.append(self.stack)
        root.append(body)
        for index, (name, title, intro, examples, tip) in enumerate(LESSONS):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            page.set_margin_end(12)
            page.append(text_label(title, 'title-2'))
            page.append(text_label(intro))
            for phrase, explanation in examples:
                example = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                example.append(text_label('“' + phrase + '”', 'heading'))
                example.append(text_label(explanation))
                page.append(example)
            page.append(Gtk.Separator())
            page.append(text_label(tip, 'dim-label'))
            scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_child(page)
            self.stack.add_titled(scroller, str(index), name)
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.previous = Gtk.Button(label='Back')
        self.previous.connect('clicked', lambda *_: self.go(-1))
        footer.append(self.previous)
        self.progress = Gtk.Label(hexpand=True)
        footer.append(self.progress)
        self.next = Gtk.Button(label='Next')
        self.next.add_css_class('suggested-action')
        self.next.connect('clicked', self.advance)
        footer.append(self.next)
        root.append(footer)
        self.set_child(root)
        self.stack.connect('notify::visible-child-name', self.changed)
        self.changed()

    def changed(self, *_):
        self.index = int(self.stack.get_visible_child_name())
        self.progress.set_text(f'{self.index + 1} of {len(LESSONS)}')
        self.previous.set_sensitive(self.index > 0)
        self.next.set_label('Done' if self.index == len(LESSONS) - 1 else 'Next')

    def go(self, offset):
        index = max(0, min(len(LESSONS) - 1, self.index + offset))
        self.stack.set_visible_child_name(str(index))

    def advance(self, *_):
        if self.index == len(LESSONS) - 1:
            self.close()
        else:
            self.go(1)
