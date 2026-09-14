"""Run the actual bar widget in an isolated shell; no audio or voice actions."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='skipper-bar-test-') as directory:
    directory = Path(directory)
    for source in Path('/usr/share/omarchy/shell').iterdir():
        if source.is_dir():
            (directory / source.name).symlink_to(source, target_is_directory=True)
    (directory / 'skipper').symlink_to(ROOT / 'config/skipper-bar', target_is_directory=True)
    (directory / 'shell.qml').write_text('''
import QtQuick
import Quickshell
import Quickshell.Wayland
import "skipper" as Skipper
ShellRoot {
    PanelWindow {
        anchors { top: true; left: true }
        implicitWidth: 440
        implicitHeight: 28
        exclusiveZone: -1
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        Skipper.BarWidget { id: widget; anchors.fill: parent; settings: ({statusPath: "/nonexistent/skipper-tutorial-test-status.json"}) }
        Timer {
            interval: 150; running: true
            onTriggered: {
                widget.readStatus({state:"Recording", updated:Date.now()/1000, session:"test", panel_epoch:1})
                if (!widget.opened) throw new Error("Recording did not reveal popup")
                complete.start()
            }
        }
        Timer {
            id: complete; interval: 100
            onTriggered: {
                widget.readStatus({state:"Ready", updated:Date.now()/1000, session:"test", panel_epoch:1,
                    completed_at:1, intent_label:"Open Gmail"})
                if (widget.opened || widget.snapshot().visible || widget.barText !== "Open Gmail · Skipper") throw new Error("Missing result")
                check.start()
            }
        }
        Timer {
            id: check; interval: 350
            onTriggered: {
                if (widget.opened || widget.snapshot().visible || widget.barText !== "Open Gmail · Skipper") throw new Error("Dismissal or intent persistence failed")
                widget.readStatus({state:"Confirm", updated:Date.now()/1000, session:"test", panel_epoch:2,
                    confirmation:{token:"abc", detail:"Test terminal"}})
                confirmCheck.start()
            }
        }
        Timer {
            id: confirmCheck; interval: 350
            onTriggered: {
                if (!widget.opened) throw new Error("Confirmation was dismissed")
                widget.close()
                expire.start()
            }
        }
        Timer {
            id: expire; interval: 200
            onTriggered: {
                if (widget.barText !== "Open Gmail · Skipper") throw new Error("Last intent did not persist")
                console.log("PASS: popup opens for recording, closes after completion, preserves intent, retains confirmation")
                Qt.quit()
            }
        }
    }
}
''')
    try:
        result = subprocess.run(['quickshell', '-p', str(directory)], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit((exc.stdout or b'').decode() + (exc.stderr or b'').decode())
    output = result.stdout + result.stderr
    if result.returncode or 'PASS:' not in output or 'Error:' in output:
        raise SystemExit(output)
    print(next(line for line in output.splitlines() if 'PASS:' in line))
