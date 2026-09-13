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
        "label": "Bring up Chrome fullscreen",
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
