"""Authored command rules, vocabulary and schemas; derived compatibility views."""
import hashlib
import json

from grammar_engine import Rule, Word, compile_grammar

TERMINAL_CLASSES = {"foot", "footclient", "alacritty", "kitty", "org.wezfurlong.wezterm", "com.mitchellh.ghostty"}

# These commands accept authored phrases only, never fuzzy or learned wording.
EXACT_ONLY_COMMANDS = {"apps:tile", "terminals:hide", "apps:hide", "window:hide"}

# Compiled against a fresh window vocabulary at recording start, not at import.
MOVE_PATTERNS = tuple(f'move {article}<window> to {other}{screen}'
                      for article in ('', 'the ')
                      for other in ('other ', 'the other ') for screen in ('screen', 'monitor', 'window'))

WINDOW_RULES = (
    Rule("focus_window", ("focus <window>", "focus the <window>",
                          "focus on <window>", "focus on the <window>",
                          "switch to <window>", "switch to the <window>",
                          "go to <window>", "go to the <window>"),
         "focus_window", (("window", "$window"),), "focus-window:{window}", "Focus {window}"),
    Rule("close_named_window", ("close <window>", "close the <window>"),
         "close_named_window", (("window", "$window"),), "close-window:{window}", "Close {window}"),
    Rule("move_named_window", MOVE_PATTERNS, "move_named_window",
         (("window", "$window"), ("monitor", "other")),
         "move-window:{window}", "Move {window} to the other screen"),
    Rule("maximize_named_window", ("maximize <window>", "maximize the <window>"),
         "maximize_named_window", (("window", "$window"), ("monitor", "current")),
         "maximize-window:{window}", "Maximize {window}"),
)

SITES = {
    "gmail": {"name": "Gmail", "url": "https://mail.google.com/", "host": "mail.google.com"},
    "github": {"name": "GitHub", "url": "https://github.com/", "host": "github.com"},
}

# Installed desktop apps are matched by exact class, never by window title.
APPS = {
    "discord": {
        "name": "Discord",
        "classes": {"discord", "Discord", "chrome-discord.com__channels_@me-Default"},
        "desktop_files": ("Discord.desktop", "discord.desktop"),
    },
    "x": {
        "name": "X (Twitter)",
        "classes": {"chrome-x.com__-Default", "chrome-twitter.com__-Default"},
        "desktop_files": ("X.desktop", "Twitter.desktop", "twitter.desktop"),
    },
}


# Non-terminals are reusable across every rule that names them.
BROWSER = Word("browser", "Chrome", ("chrome", "chromium", "google chrome"))
APP_WORDS = (Word("discord", "Discord", ("discord",)), Word("x", "X (Twitter)", ("x", "twitter")))
DESTINATION_FORMS = {"gmail": ("gmail", "g mail"), "github": ("github", "git hub")}
VOCABULARY = {
    "destination": tuple(Word(key, site["name"], DESTINATION_FORMS.get(key, (key,)))
                         for key, site in SITES.items()),
    "browser": (BROWSER,),
    "app": APP_WORDS,
    "window_app": (BROWSER,) + APP_WORDS,
}

# Argument values are registry IDs or explicit targeting/presentation policies.
SCHEMAS = {
    "open_destination": {"destination": tuple(SITES)},
    "open_application": {"application": ("browser", "discord", "x"),
                         "presentation": ("normal", "maximized", "fullscreen")},
    "create_terminal": {},
    "close_window": {"application": ("browser", "discord", "x", "terminal"),
                     "selection": ("most_recent", "current")},
    "maximize_window": {"application": ("browser", "discord", "x", "any"),
                        "selection": ("most_recent", "current"),
                        "monitor": ("main", "current")},
    "move_window": {"selection": ("current",), "monitor": ("other",)},
    "move_application": {"application": ("browser", "discord", "x"),
                         "selection": ("most_recent",), "monitor": ("other",)},
    "show_windows": {},
    "tile_windows": {"workspace": ("current",)},
    "tile_terminals": {"workspace": ("current",)},
    "tile_browsers": {"workspace": ("current",)},
    "tile_apps": {"workspace": ("current",)},
    "hide_windows": {"workspace": ("current",), "category": ("terminals", "apps")},
    "hide_window": {"selection": ("current",)},
}

RULES = (
    Rule("open_destination", ("open <destination>", "bring up <destination>"),
         "open_destination", (("destination", "$destination"),), "site:{destination}", "Open {destination}"),
    Rule("open_browser", ("open <browser>", "launch <browser>", "focus <browser>", "switch to <browser>"),
         "open_application", (("application", "$browser"), ("presentation", "maximized")), "browser", "Open Chrome"),
    Rule("present_browser", ("bring up <browser>",), "open_application",
         (("application", "$browser"), ("presentation", "maximized")),
         "browser_fullscreen", "Bring up Chrome with tabs visible"),
    Rule("open_app", ("open <app>", "bring up <app>", "focus <app>", "switch to <app>"), "open_application",
         (("application", "$app"), ("presentation", "maximized")), "{app}", "Open {app}"),
    Rule("close_app", ("close <window_app>",), "close_window",
         (("application", "$window_app"), ("selection", "most_recent")),
         "close:{window_app}", "Close {window_app} window"),
    Rule("move_app", tuple(p.replace('<window>', '<window_app>') for p in MOVE_PATTERNS),
         "move_application", (("application", "$window_app"), ("selection", "most_recent"), ("monitor", "other")),
         "move-app:{window_app}", "Move {window_app} to the other screen"),
    Rule("maximize_app", ("maximize <window_app>",), "maximize_window",
         (("application", "$window_app"), ("selection", "most_recent"), ("monitor", "current")),
         "maximize:{window_app}", "Maximize {window_app} window"),
    Rule("create_terminal", ("open a new terminal", "open a terminal", "open terminal", "open new terminal"),
         "create_terminal", (), "terminal:new", "Open a new terminal"),
    Rule("close_terminal", ("close terminal", "close the terminal", "close a terminal"), "close_window",
         (("application", "terminal"), ("selection", "most_recent")), "close:terminal", "Close the most recent terminal"),
    Rule("close_current_terminal", ("close this terminal",), "close_window",
         (("application", "terminal"), ("selection", "current")), "close:terminal_current", "Close this terminal"),
    Rule("maximize_current_window", ("maximize this window", "maximize the current window"), "maximize_window",
         (("application", "any"), ("selection", "current"), ("monitor", "current")),
         "maximize:current_window", "Maximize this window"),
    Rule("move_window", ("move to other screen", "move window to other screen", "move to the other screen",
                         "move window to the other screen", "move this window to the other screen"),
         "move_window", (("selection", "current"), ("monitor", "other")), "move:other_screen", "Move window to the other screen"),
    Rule("show_windows", ("show all windows", "show all open windows", "show all open window"),
         "show_windows", (), "windows", "Show all open windows"),
    Rule("tile_windows", ("tile open windows", "tile all open windows", "tile windows", "tile all windows"),
         "tile_windows", (("workspace", "current"),), "windows:tile", "Tile open windows"),
    Rule("tile_terminals", ("tile all the terminals", "tile all terminals", "tile terminals",
                            "tile the terminals", "tile open terminals", "tile all open terminals"),
         "tile_terminals", (("workspace", "current"),), "terminals:tile",
         "Tile terminals and minimize other windows"),
    Rule("tile_browsers", ("tile all browsers", "tile all the browsers", "tile browsers",
                           "tile the browsers", "tile open browsers", "tile all browser windows"),
         "tile_browsers", (("workspace", "current"),), "browsers:tile",
         "Tile browsers and minimize other windows"),
    Rule("hide_terminals", ("hide all terminals",), "hide_windows",
         (("workspace", "current"), ("category", "terminals")), "terminals:hide", "Hide all terminals"),
    Rule("hide_apps", ("hide all apps",), "hide_windows",
         (("workspace", "current"), ("category", "apps")), "apps:hide", "Hide all non-terminal apps"),
    Rule("hide_current_window", ("hide this window",), "hide_window",
         (("selection", "current"),), "window:hide", "Hide this window"),
    Rule("tile_apps", ("tile all apps", "tile the apps"),
         "tile_apps", (("workspace", "current"),), "apps:tile",
         "Tile non-terminal apps and minimize terminals"),
)

EXPANSIONS = compile_grammar(RULES, VOCABULARY, SCHEMAS)
# Compatibility views keep current execution IDs and version-1 learned aliases working.
INTENTS = {}
GRAMMAR = {}
STRUCTURED_INTENTS = {}
for expansion in EXPANSIONS:
    existing = STRUCTURED_INTENTS.setdefault(expansion.command, expansion.intent)
    if existing != expansion.intent:
        raise ValueError(f"Conflicting execution ID: {expansion.command}")
    entry = INTENTS.setdefault(expansion.command, {"label": expansion.label, "phrases": []})
    if expansion.phrase not in entry["phrases"]:
        entry["phrases"].append(expansion.phrase)
    GRAMMAR[expansion.phrase] = expansion.command

GRAMMAR_REVISION = hashlib.sha256(json.dumps([
    {"phrase": e.phrase, "rule": e.rule_id, "pattern": e.pattern,
     "bindings": e.bindings, "intent": e.intent.to_dict(), "command": e.command}
    for e in EXPANSIONS
], sort_keys=True).encode()).hexdigest()[:16]
