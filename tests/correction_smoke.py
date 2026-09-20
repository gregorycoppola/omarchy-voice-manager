"""Inline dropdown entry and real D-Bus correction save, isolated from user data."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import VoiceRuntime
from corrections import Corrections
from gi.repository import GLib

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    runtime = VoiceRuntime(root, root / 'status.json')
    runtime.set_application_id('io.github.gregorycoppola.Skipper.CorrectionTest')
    runtime.register(None)
    with patch.object(runtime, 'show_correction'):
        runtime.offer_correction('towel those apps', {}, str(root / 'test.wav'))
    for source in Path('/usr/share/omarchy/shell').iterdir():
        if source.is_dir():
            (root / source.name).symlink_to(source, target_is_directory=True)
    (root / 'skipper').symlink_to(ROOT / 'config/skipper-bar', target_is_directory=True)
    source = '''
import QtQuick
import QtTest
import Quickshell
import Quickshell.Wayland
import "skipper" as Skipper
ShellRoot {
    TestCase { id: helper; when: false }
    PanelWindow {
        id: panel
        anchors { top: true; left: true }
        implicitWidth: 440; implicitHeight: 28; exclusiveZone: -1
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        Skipper.BarWidget {
            id: widget; anchors.fill: parent
            settings: ({statusPath: STATUS_PATH, runtimeAppId: "io.github.gregorycoppola.Skipper.CorrectionTest"})
        }
        property int phase: 0
        property int holdTicks: 0
        Timer {
            interval: 100; running: true; repeat: true
            onTriggered: {
                if (panel.phase === 0 && widget.state === "Correction" && widget.opened) {
                    var field = helper.findChild(widget, "correctionWords")
                    if (!field) throw new Error("No inline correction field")
                    helper.parent = field
                    field.forceActiveFocus()
                    field.text = "tile all app"
                    field.cursorPosition = field.text.length
                    helper.keyClick(Qt.Key_S)
                    if (field.text !== "tile all apps") throw new Error("Dropdown did not receive typing: " + field.text + " focus=" + field.activeFocus)
                    widget.submitCorrection("preview")
                    panel.phase = 1
                } else if (panel.phase === 1 && widget.correctionMatches) {
                    if (!helper.findChild(widget, "saveCorrection").enabled) throw new Error("Save not enabled")
                    widget.submitCorrection("save")
                    panel.phase = 2
                } else if (panel.phase === 2 && widget.state === "Ready") {
                    if (widget.opened) throw new Error("Saved form did not close")
                    widget.action("type-command")
                    panel.phase = 3
                } else if (panel.phase === 3 && widget.state === "TextEntry" && widget.snapshot().writtenOpen) {
                    var written = helper.findChild(widget, "writtenWords")
                    helper.parent = written
                    written.forceActiveFocus()
                    written.text = "open chrom"
                    written.cursorPosition = written.text.length
                    helper.keyClick(Qt.Key_E)
                    if (written.text !== "open chrome") throw new Error("Written mode did not receive typing")
                    panel.phase = 31
                } else if (panel.phase === 31) {
                    panel.holdTicks++
                    if (panel.holdTicks === 1) {
                        var overlay = helper.findChild(widget, "writtenPanel")
                        helper.mouseClick(overlay.contentItem, 1, 1)
                        widget.action("type-command")
                        widget.close()
                    }
                    if (!widget.snapshot().writtenOpen) throw new Error("Typed box dismissed before Enter/Escape")
                    if (helper.findChild(widget, "writtenWords").text !== "open chrome") throw new Error("Draft lost")
                    if (panel.holdTicks > 35) {
                        helper.keyClick(Qt.Key_Return)
                        panel.phase = 4
                    }
                } else if (panel.phase === 4 && widget.state === "Ready") {
                    if (widget.opened) throw new Error("Written command did not dismiss dropdown")
                    if (widget.snapshot().writtenOpen) throw new Error("Enter did not close input")
                    widget.action("type-command")
                    panel.phase = 5
                } else if (panel.phase === 5 && widget.state === "TextEntry" && widget.snapshot().writtenOpen) {
                    helper.parent = helper.findChild(widget, "writtenWords")
                    helper.keyClick(Qt.Key_Escape)
                    panel.phase = 6
                } else if (panel.phase === 6 && widget.state === "Ready") {
                    if (widget.snapshot().writtenOpen) throw new Error("Escape did not close input")
                    console.log("PASS: centered input persists through wait, outside click and repeated shortcut; Enter executes, Escape cancels")
                    Qt.quit()
                }
            }
        }
    }
}
'''.replace('STATUS_PATH', json.dumps(str(runtime.status_path)))
    (root / 'shell.qml').write_text(source)
    loop = GLib.MainLoop()
    with (root / 'output.log').open('w') as output, patch.object(runtime, 'execute', return_value='Opened browser') as execute, patch('runtime.capture_window_context', return_value={}), patch.object(runtime, 'focused_monitor', return_value=''):
        process = subprocess.Popen(['quickshell', '-p', str(root)], stdout=output, stderr=subprocess.STDOUT)
        def poll():
            if process.poll() is not None:
                loop.quit()
                return False
            return True
        def timeout():
            process.kill()
            loop.quit()
            return False
        GLib.timeout_add(100, poll)
        timer = GLib.timeout_add_seconds(12, timeout)
        loop.run()
        if process.poll() is None:
            process.kill()
        process.wait()
        if process.returncode == 0:
            GLib.source_remove(timer)
        execute.assert_called_once_with('browser', {}, None)
    output = (root / 'output.log').read_text()
    assert process.returncode == 0 and 'PASS:' in output and 'Error:' not in output, output
    rule = Corrections(root / 'corrections.json').rules['towel those apps']
    assert rule['said'] == rule['meant'] == 'tile all apps'
    assert rule['intent']['type'] == 'tile_apps'
    print(next(line for line in output.splitlines() if 'PASS:' in line))
