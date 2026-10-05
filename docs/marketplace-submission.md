# Marketplace submission draft

Status: GPL-3.0-only is selected and packaging validation passes. This is the
completed proposed submission; the checked owner statements below require owner
confirmation before the issue is filed.

Title: `[Plugin]: Skipper`

```markdown
### Repository URL

https://github.com/gregorycoppola/omarchy-voice-manager

### Category

Productivity

### Tags

bar, hyprland, launcher

### Suggest a missing tag

_No response_

### Maintainer notes

Skipper is a text-first desktop command picker with a Quickshell bar widget and
companion Python runtime, licensed GPL-3.0-only. Hierarchical menus support
window operations, website and file opening, audio-device selection, and explicit
night light, Wi-Fi, and paired Bluetooth controls.

Shared intent definitions and their catalog reader are bundled in the plugin
repository, with their license and pinned source revision. Installation does not
fetch another GitHub repository or download a speech model. Manual setup is
required: plugin_setup.py prepares a per-user Python environment using system
PyGObject/Cairo and installs launchers. Omarchy installation does not run setup
automatically. Optional --shortcut and --autostart flags add Super+R and a login
launcher. System package requirements and removal are documented in the README.

Capabilities include Hyprland window metadata/control, app launching, local
browser-history and recent-file reading, home-directory filename search,
terminal process inspection for close confirmations, and optional Playwright
browser-tab integration. System controls use the available local backends.
Personal history and preferences remain outside the plugin checkout. External
apps and opened websites have their own network behavior.

Custom speech recognition has been removed. Optional external voice input is
planned. Tested on Linux aarch64; x86_64 has not been tested. No preview image is
supplied.

### Submission checklist

- [x] The repository is public and contains installation and removal instructions.
- [x] I have documented the plugin license and any external dependencies.
- [x] I confirm that I own or have permission to submit this plugin and its preview assets.
- [x] The plugin does not overwrite user configuration without explicit consent.
- [x] I understand that approval is for listing and is not a security review.
```

Review these proposed statements with the owner and submit only after explicit
approval of the completed title/body and all five checklist items. The reference process is:
https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md
