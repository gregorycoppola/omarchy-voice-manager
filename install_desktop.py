"""Install Keety's per-user launcher without root or system package changes."""
import os
from pathlib import Path
import shlex


def install(root, home, data_home):
    root = Path(root).resolve()
    launcher = root / "launch.sh"
    if not launcher.is_file():
        raise ValueError("Run this installer from a complete Keety checkout")
    binary = Path(home) / ".local/bin/keety"
    desktop = Path(data_home) / "applications/io.github.gregorycoppola.Keety.desktop"
    binary.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexec " + shlex.quote(str(launcher)) + ' "$@"\n')
    binary.chmod(0o755)
    # Desktop Exec has its own quoting rules, distinct from shell quoting.
    executable = str(launcher).replace("\\", "\\\\\\\\").replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    desktop.write_text(
        "[Desktop Entry]\nType=Application\nName=Keety\n"
        "Comment=Record and transcribe speech locally\n"
        f'Exec="{executable}"\n'
        "Icon=audio-input-microphone\nTerminal=false\n"
        "Categories=AudioVideo;Audio;\nStartupNotify=true\n"
        "StartupWMClass=io.github.gregorycoppola.Keety\n"
    )
    return binary, desktop


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    for path in install(root, home, data):
        print(f"Installed {path}")
