import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "greg.skipper"
    readonly property string pluginRoot: decodeURIComponent(Qt.resolvedUrl("../../").toString().replace(/^file:\/\//, "")).replace(/\/$/, "")
    property string userId: ""
    readonly property string defaultStatusPath: userId ? (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/skipper-" + userId + "-status.json" : ""
    Process {
        command: ["id", "-u"]
        running: true
        stdout: StdioCollector { onStreamFinished: root.userId = text.trim() }
    }
    property var status: ({})
    property string seenEvent: ""
    property bool manual: false
    property string recentIntent: ""
    readonly property string barText: state === "Recording" ? "● Skipper" : recentIntent ? recentIntent + " · Skipper" : "Skipper"
    readonly property bool alive: (clock.date.getTime() / 1000 - (status.updated || 0)) < 8
    readonly property string state: alive ? (status.state || "Stopped") : "Stopped"
    readonly property bool working: state === "Recording" || state === "Working" || state === "Loading"
    readonly property bool opened: popup.open
    readonly property string screenName: button.QsWindow.window && button.QsWindow.window.screen
                                        ? button.QsWindow.window.screen.name : ""
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function snapshot() { return {opened: popup.open, visible: popup.visible, state: state, barText: barText, screen: screenName} }
    function open() { manual = true; dismissTimer.stop(); popup.open = true }
    function close() { manual = false; popup.open = false; dismissTimer.stop() }
    function togglePanel() { if (opened) close(); else open() }
    function action(name, token) {
        var args = ["gapplication", "action", "io.github.gregorycoppola.Skipper", name]
        if (token !== undefined) args.push("'" + token + "'") // Runtime-generated hex token only.
        Quickshell.execDetached(args)
    }
    function readStatus(value) {
        var previousCompletion = status.completed_at || 0
        var previousState = status.state || "Stopped"
        var event = String(value.session || "") + ":" + String(value.panel_epoch || 0)
        var newEvent = event !== seenEvent
        seenEvent = event
        status = value
        // Use the incoming payload directly: derived QML bindings may update later.
        if (value.intent_label) recentIntent = value.intent_label
        var completed = (value.completed_at && value.completed_at !== previousCompletion)
                     || (previousState === "Working" && value.state === "Ready")
        if (completed && value.state === "Ready") {
            root.close()
            return
        }
        if (newEvent && value.panel_epoch > 0 && (!value.monitor || value.monitor === screenName)) {
            manual = false
            popup.open = true
        }
        if (value.state === "Recording" || value.state === "Working" || value.state === "Confirm" || value.state === "Loading") {
            dismissTimer.stop()
        } else if (popup.open && !manual && !dismissTimer.running) {
            dismissTimer.interval = value.state === "Error" ? 6000 : 2500
            dismissTimer.start()
        }
    }

    SystemClock { id: clock; precision: SystemClock.Seconds }
    Timer { id: dismissTimer; interval: 2500; onTriggered: root.close() }
    onAliveChanged: if (!alive && popup.open && !manual) dismissTimer.restart()
    FileView {
        path: root.setting("statusPath", root.defaultStatusPath)
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { root.readStatus(JSON.parse(text())) } catch (e) { root.status = ({}) }
        }
    }
    IpcHandler {
        target: "greg.skipper"
        function open(): void { root.open() }
        function close(): void { root.broadcast("close") }
        function toggle(): void { root.togglePanel() }
        function inspect(): string { return JSON.stringify(root.snapshot()) }
        function inspectAll(): string {
            var widgets = root.bar ? root.bar.moduleWidgets(root.moduleName) : [root]
            return JSON.stringify(widgets.map(function(widget) { return widget.snapshot() }))
        }
    }
    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.barText
        active: root.opened || root.working || root.state === "Confirm" || root.state === "Error"
        activeColor: root.state === "Recording" ? "#a6da95" : root.state === "Error" ? Color.urgent : foreground
        tooltipText: "Hold Super + R to talk · " + root.state
        onPressed: function(b) { root.togglePanel() }
    }
    PopupCard {
        id: popup
        anchorItem: button
        bar: root.bar
        owner: root
        // A passive popup: no keyboard focus grab, including automatic recording reveals.
        triggerMode: "hover"
        // Do not leave a fading result window over the app after execution.
        visible: open
        contentWidth: fittedContentWidth(Style.space(440))
        contentHeight: fittedContentHeight(content.implicitHeight)

        Flickable {
            anchors.fill: parent
            contentHeight: content.implicitHeight
            clip: true
            Column {
                id: content
                width: parent.width
                spacing: Style.space(12)
                Row {
                    width: parent.width
                    Text {
                        width: parent.width - hideButton.width
                        text: "Skipper · " + root.state
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Button { id: hideButton; text: "×"; onClicked: root.close() }
                }
                Rectangle {
                    width: parent.width
                    height: Style.space(48)
                    radius: Style.space(6)
                    color: Qt.alpha(Color.foreground, 0.04)
                    Row {
                        anchors.fill: parent
                        anchors.margins: Style.space(8)
                        spacing: Style.space(3)
                        Repeater {
                            model: 48
                            Rectangle {
                                required property int index
                                width: Math.max(1, (parent.width - 47 * parent.spacing) / 48)
                                height: Math.max(2, Math.min(1, Math.max(0, (root.status.levels || [])[index] || 0)) * parent.height)
                                anchors.verticalCenter: parent.verticalCenter
                                radius: 1
                                color: root.state === "Recording" ? Color.accent : Color.muted
                            }
                        }
                    }
                }
                Text {
                    width: parent.width
                    text: root.status.transcript || (root.state === "Recording" ? "Listening…" : "Hold Super + R to speak.")
                    textFormat: Text.PlainText
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    wrapMode: Text.Wrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                }
                Rectangle { width: parent.width; height: 1; color: Qt.alpha(Color.foreground, 0.12) }
                Text {
                    width: parent.width
                    text: root.status.intent_label || (root.state === "Working" ? "Understanding…" : "No intent yet")
                    textFormat: Text.PlainText
                    color: root.status.intent_label ? Color.accent : Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    font.bold: true
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    visible: !!root.status.intent
                    text: {
                        var intent = root.status.intent
                        if (!intent) return ""
                        var args = Object.keys(intent.arguments || {}).map(function(key) { return key + "=" + intent.arguments[key] })
                        return intent.type + "(" + args.join(", ") + ")"
                    }
                    textFormat: Text.PlainText
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body * 0.85
                    wrapMode: Text.WrapAnywhere
                }
                Text {
                    width: parent.width
                    text: root.alive ? (root.status.message || "") : "Skipper is stopped. First install? Run python " + root.pluginRoot + "/plugin_setup.py install in a terminal."
                    textFormat: Text.PlainText
                    color: root.state === "Error" ? Color.urgent : Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body * 0.85
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
                Column {
                    visible: root.state === "Confirm" && !!root.status.confirmation
                    width: parent.width
                    spacing: Style.space(8)
                    Text {
                        width: parent.width
                        text: root.status.confirmation ? "Close terminal: " + root.status.confirmation.detail : ""
                        textFormat: Text.PlainText
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        wrapMode: Text.Wrap
                    }
                    Row {
                        spacing: Style.space(8)
                        Button { text: "Cancel"; bordered: true; onClicked: root.action("cancel", root.status.confirmation.token) }
                        Button { text: "Close terminal"; onClicked: root.action("confirm", root.status.confirmation.token) }
                    }
                }
                Row {
                    spacing: Style.space(8)
                    Button {
                        text: "Tutorial"
                        onClicked: {
                            var launcher = root.setting("explorerLauncher", root.pluginRoot + "/launch-explorer.sh")
                            if (launcher) Quickshell.execDetached([launcher, "--tutorial"])
                            root.close()
                        }
                    }
                    Button {
                        text: "Explorer"
                        onClicked: {
                            var launcher = root.setting("explorerLauncher", root.pluginRoot + "/launch-explorer.sh")
                            if (launcher) Quickshell.execDetached([launcher])
                            root.close()
                        }
                    }
                    Button {
                        text: root.alive && root.state !== "Stopped" ? "Quit" : "Start Skipper"
                        onClicked: {
                            if (root.alive && root.state !== "Stopped") root.action("quit")
                            else {
                                var launcher = root.setting("launcher", root.pluginRoot + "/launch.sh")
                                if (launcher) Quickshell.execDetached([launcher, "--show"])
                            }
                        }
                    }
                }
            }
        }
    }
}
