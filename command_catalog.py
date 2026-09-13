"""The complete accepted vocabulary and fixed website destinations."""

SITES = {
    "gmail": {"name": "Gmail", "url": "https://mail.google.com/", "host": "mail.google.com"},
    "github": {"name": "GitHub", "url": "https://github.com/", "host": "github.com"},
}

# Stable intent IDs connect phrases to fixed OS actions.
INTENTS = {
    "browser": {
        "label": "Open Chrome",
        "phrases": [
            "open chrome",
            "launch chrome",
            "focus chrome",
            "switch to chrome",
            "open chromium",
            "open google chrome"
        ]
    },
    "browser_fullscreen": {
        "label": "Bring up Chrome with tabs visible",
        "phrases": [
            "bring up chrome",
            "bring up chromium",
            "bring up google chrome"
        ]
    },
    "discord": {
        "label": "Open Discord",
        "phrases": [
            "bring up discord",
            "open discord"
        ]
    },
    "windows": {
        "label": "Show all open windows",
        "phrases": [
            "show all windows",
            "show all open windows",
            "show all open window"
        ]
    },
    "site:gmail": {
        "label": "Open Gmail",
        "phrases": [
            "open gmail",
            "bring up gmail",
            "open g mail",
            "bring up g mail"
        ]
    },
    "site:github": {
        "label": "Open GitHub",
        "phrases": [
            "open github",
            "bring up github",
            "open git hub",
            "bring up git hub"
        ]
    },
    "x": {
        "label": "Open X (Twitter)",
        "phrases": [
            "open x",
            "bring up x",
            "open twitter",
            "bring up twitter"
        ]
    },
    "close:discord": {
        "label": "Close Discord window",
        "phrases": [
            "close discord"
        ]
    },
    "close:x": {
        "label": "Close X (Twitter) window",
        "phrases": [
            "close x",
            "close twitter"
        ]
    },
    "close:browser": {
        "label": "Close Chrome window",
        "phrases": [
            "close chrome",
            "close chromium",
            "close google chrome"
        ]
    },
    "maximize:browser": {
        "label": "Maximize Chrome window",
        "phrases": [
            "maximize chrome",
            "maximize chromium",
            "maximize google chrome"
        ]
    },
    "maximize:discord": {
        "label": "Maximize Discord window",
        "phrases": [
            "maximize discord"
        ]
    },
    "maximize:x": {
        "label": "Maximize X (Twitter) window",
        "phrases": [
            "maximize x",
            "maximize twitter"
        ]
    },
    "terminal:new": {
        "label": "Open a new terminal",
        "phrases": [
            "open a new terminal",
            "open a terminal",
            "open terminal",
            "open new terminal"
        ]
    },
    "close:terminal": {
        "label": "Close the most recent terminal",
        "phrases": [
            "close terminal",
            "close the terminal",
            "close a terminal"
        ]
    },
    "close:terminal_current": {
        "label": "Close this terminal",
        "phrases": [
            "close this terminal"
        ]
    },
    "maximize:current_window": {
        "label": "Maximize this window",
        "phrases": ["maximize this window", "maximize the current window"]
    },
    "windows:tile": {
        "label": "Tile open windows",
        "phrases": ["tile open windows", "tile all open windows", "tile windows", "tile all windows"]
    },
    "move:other_screen": {
        "label": "Move window to the other screen",
        "phrases": [
            "move to other screen",
            "move window to other screen",
            "move to the other screen",
            "move window to the other screen",
            "move this window to the other screen"
        ]
    }
}

GRAMMAR = {phrase: intent for intent, entry in INTENTS.items() for phrase in entry["phrases"]}


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
