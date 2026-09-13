"""The complete accepted vocabulary and fixed website destinations."""

SITES = {
    "gmail": {"name": "Gmail", "url": "https://mail.google.com/", "host": "mail.google.com"},
    "github": {"name": "GitHub", "url": "https://github.com/", "host": "github.com"},
}

GRAMMAR = {
    "bring up discord": "discord",
    "open discord": "discord",
    "show all windows": "windows",
    "show all open windows": "windows",
    "show all open window": "windows",
    "open chrome": "browser",
    "bring up chrome": "browser_fullscreen",
    "launch chrome": "browser",
    "focus chrome": "browser",
    "switch to chrome": "browser",
    "open chromium": "browser",
    "bring up chromium": "browser_fullscreen",
    "open google chrome": "browser",
    "bring up google chrome": "browser_fullscreen",
    "open gmail": "site:gmail",
    "bring up gmail": "site:gmail",
    "open g mail": "site:gmail",
    "bring up g mail": "site:gmail",
    "open github": "site:github",
    "bring up github": "site:github",
    "open git hub": "site:github",
    "bring up git hub": "site:github",
}
