"""Authored command rules, vocabulary and schemas; derived compatibility views."""
import hashlib
import json

from grammar_engine import Rule, Word, compile_grammar

TERMINAL_CLASSES = {"foot", "footclient", "alacritty", "kitty", "org.wezfurlong.wezterm", "com.mitchellh.ghostty"}

# Compiled against a fresh window vocabulary at recording start, not at import.
WINDOW_RULES = (
    Rule("focus_window", ("focus <window>", "focus the <window>",
                          "switch to <window>", "switch to the <window>",
                          "go to <window>", "go to the <window>"),
         "focus_window", (("window", "$window"),), "focus-window:{window}", "Focus {window}"),
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
    "show_windows": {},
    "tile_windows": {"workspace": ("current",)},
}

RULES = (
    Rule("open_destination", ("open <destination>", "bring up <destination>"),
         "open_destination", (("destination", "$destination"),), "site:{destination}", "Open {destination}"),
    Rule("open_browser", ("open <browser>", "launch <browser>", "focus <browser>", "switch to <browser>"),
         "open_application", (("application", "$browser"), ("presentation", "normal")), "browser", "Open Chrome"),
    Rule("present_browser", ("bring up <browser>",), "open_application",
         (("application", "$browser"), ("presentation", "maximized")),
         "browser_fullscreen", "Bring up Chrome with tabs visible"),
    Rule("open_app", ("open <app>", "bring up <app>"), "open_application",
         (("application", "$app"), ("presentation", "fullscreen")), "{app}", "Open {app}"),
    Rule("close_app", ("close <window_app>",), "close_window",
         (("application", "$window_app"), ("selection", "most_recent")),
         "close:{window_app}", "Close {window_app} window"),
    Rule("maximize_app", ("maximize <window_app>",), "maximize_window",
         (("application", "$window_app"), ("selection", "most_recent"), ("monitor", "main")),
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
