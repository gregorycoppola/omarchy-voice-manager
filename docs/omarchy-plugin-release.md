# Skipper plugin release status

The repository is public. The root `manifest.json` loads
`config/skipper-bar/BarWidget.qml` as `greg.skipper`, a third-party Omarchy bar
widget. The nested manifest supports the existing development-only bar installer.
Both manifests use version 0.2.0.

The README documents Git-based plugin installation and a separate manual setup
command. `plugin_setup.py` installs Python dependencies and the pinned model
outside the checkout, plus per-user launchers. Shortcut and autostart installation
are explicit flags. Removal preserves saved data and user-modified files.

The launcher also supports the existing development virtual environment. The bar
has defaults for launchers and status paths, so new plugin installs do not depend
on the author's shell.json. App-opening actions support single-monitor systems;
SKIPPER_MAIN_MONITOR can select a particular output.

Remaining before marketplace submission:

- Choose and add a license.
- Review the owner statements and completed submission in
  [marketplace-submission.md](marketplace-submission.md).
- Push the completed release and obtain explicit approval to file the submission.
- Address any feedback from the marketplace automation and maintainers.

Listing requires maintainer approval. It does not make Skipper a bundled Omarchy
component or entitle it to use the reserved `omarchy.*` namespace. x86_64 support
has not yet been tested.

References checked 2026-09-14:

- https://omarchy.org/manual/shell-plugins/
- https://plugins.omarchy.org/publish.html
- https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md
