import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

BarWidget {
    id: root
    moduleName: "greg.keety"
    property var status: ({})
    readonly property bool alive: (clock.date.getTime() / 1000 - (status.updated || 0)) < 16
    readonly property string state: alive ? (status.state || "Stopped") : "Stopped"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    SystemClock { id: clock; precision: SystemClock.Seconds }
    FileView {
        path: root.setting("statusPath", "")
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { root.status = JSON.parse(text()) } catch (e) { root.status = ({}) }
        }
    }
    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "Keety · " + root.state
        active: root.state === "Recording"
        tooltipText: "Hold Super + R to talk. Click for history and settings." +
                     (root.alive && root.status.message ? "\n" + root.status.message : "")
        onPressed: function(b) {
            var launcher = root.setting("launcher", "")
            if (launcher !== "") Quickshell.execDetached([launcher, "--show"])
        }
    }
}
