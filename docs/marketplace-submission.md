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

bar, hyprland, ai

### Suggest a missing tag

_No response_

### Maintainer notes

Skipper is a local hold-to-talk voice command plugin with a Quickshell bar widget
and a companion Python process, licensed GPL-3.0-only. Third-party model and
test-protocol licenses are documented separately. Manual setup is required: plugin_setup.py creates
a per-user Python environment, installs pinned dependencies, and downloads a
revision-pinned, checksum-verified speech model (about 639 MiB). Omarchy plugin
installation does not run setup automatically. The optional --shortcut and
--autostart flags install Super+R integration and a login launcher. System
packages are not installed by the setup script. Removal and retained data are
documented in the README.

Capabilities: microphone recording while held, local recordings/transcripts,
Hyprland window metadata/control, app launching, terminal process-tree inspection
for close confirmations, and optional Playwright browser-tab integration.
Transcription runs on CPU without a cloud service. Tested on Linux aarch64;
x86_64 has not been tested. No preview image is supplied.

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
