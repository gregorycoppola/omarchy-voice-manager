"""Install Keety's per-user launcher without root or system package changes."""
import os
from pathlib import Path
import shlex


def install(root, home, data_home, *, explorer=False):
    root = Path(root).resolve()
    launcher = root / ("launch-explorer.sh" if explorer else "launch.sh")
    if not launcher.is_file():
        raise ValueError("Run this installer from a complete Keety checkout")
    name = "Keety Explorer" if explorer else "Keety"
    app_id = "io.github.gregorycoppola.Keety" + (".Explorer" if explorer else "")
    binary = Path(home) / ".local/bin" / ("keety-explorer" if explorer else "keety")
    desktop = Path(data_home) / "applications" / f"{app_id}.desktop"
    binary.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexec " + shlex.quote(str(launcher)) + ' "$@"\n')
    binary.chmod(0o755)
    # Desktop Exec has its own quoting rules, distinct from shell quoting.
    executable = str(launcher).replace("\\", "\\\\\\\\").replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    comment = ("Explore voice grammars, vocabulary and intents" if explorer
               else "Record and transcribe speech locally")
    desktop.write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\n"
        f"Comment={comment}\n"
        f'Exec="{executable}"\n'
        "Icon=audio-input-microphone\nTerminal=false\n"
        "Categories=AudioVideo;Audio;\nStartupNotify=true\n"
        f"StartupWMClass={app_id}\n"
    )
    return binary, desktop


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    for explorer in (False, True):
        for path in install(root, home, data, explorer=explorer):
            print(f"Installed {path}")
