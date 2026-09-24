import "CommandSearch.js" as CommandSearch
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
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
    property string correctionToken: ""
    property string writtenToken: ""
    property bool writtenOpen: false
    property int historySelection: -1
    readonly property var historyMatches: CommandSearch.search(
        status.written_entry ? (status.written_entry.history || []) : [], writtenWords.text)
    function selectHistory(delta) {
        if (!historyMatches.length) return
        historySelection = (historySelection + delta + historyMatches.length) % historyMatches.length
    }
    function recallHistory() {
        if (historySelection < 0 || historySelection >= historyMatches.length) return
        var recalled = historyMatches[historySelection]
        writtenWords.text = recalled
        writtenWords.cursorPosition = recalled.length
        historySelection = -1
        writtenWords.forceActiveFocus()
    }
    readonly property bool correctionMatches: !!status.correction && !!status.correction.preview
        && status.correction.preview.said === correctionWords.text.trim()
        && status.correction.preview.meant === correctionWords.text.trim()
    readonly property string barText: state === "Recording" ? "● Skipper" : recentIntent ? recentIntent + " · Skipper" : "Skipper"
    readonly property bool alive: (clock.date.getTime() / 1000 - (status.updated || 0)) < 8
    readonly property string state: alive ? (status.state || "Stopped") : "Stopped"
    readonly property bool working: state === "Recording" || state === "Working" || state === "Loading"
    readonly property bool opened: popup.open
    readonly property string screenName: button.QsWindow.window && button.QsWindow.window.screen
                                        ? button.QsWindow.window.screen.name : ""
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function snapshot() { return {opened: popup.open, visible: popup.visible, state: state, barText: barText, screen: screenName, writtenOpen: writtenOpen, writtenFocused: writtenWords.activeFocus} }
    function open() { manual = true; dismissTimer.stop(); popup.open = true }
    function close() { manual = false; popup.open = false; dismissTimer.stop() }
    function togglePanel() { if (opened) close(); else open() }
    function action(name, token) {
        var args = ["gapplication", "action", root.setting("runtimeAppId", "io.github.gregorycoppola.Skipper"), name]
        if (token !== undefined) args.push(JSON.stringify(token)) // GVariant string; no shell.
        Quickshell.execDetached(args)
    }
    function submitCorrection(operation) {
        if (!status.correction) return
        root.action("correct-command", JSON.stringify({token: status.correction.token,
            operation: operation, said: correctionWords.text, meant: correctionWords.text}))
    }
    function submitWritten() {
        if (!status.written_entry) return
        if (historySelection >= 0) recallHistory()
        writtenOpen = false
        root.action("submit-written", JSON.stringify({token: status.written_entry.token, text: writtenWords.text}))
    }
    function readStatus(value) {
        var previousCompletion = status.completed_at || 0
        var previousState = status.state || "Stopped"
        var event = String(value.session || "") + ":" + String(value.panel_epoch || 0)
        var newEvent = event !== seenEvent
        seenEvent = event
        status = value
        if (value.correction && value.correction.token !== correctionToken) {
            correctionToken = value.correction.token
            correctionWords.text = ""
        }
        if (value.written_entry && value.written_entry.token !== writtenToken) {
            historySelection = -1
            writtenToken = value.written_entry.token
            writtenWords.text = value.written_entry.text || ""
        }
        if (value.state === "TextEntry" && value.written_entry && (!value.monitor || value.monitor === screenName)) {
            popup.open = false
            dismissTimer.stop()
            if (newEvent) {
                writtenOpen = true
                Qt.callLater(function() { writtenWords.forceActiveFocus() })
            }
            return
        }
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
            popup.focusPrimed = false
            popup.open = true
            Qt.callLater(function() {
                if (value.state === "TextEntry") writtenWords.forceActiveFocus()
                else if (value.state === "Correction") correctionWords.forceActiveFocus()
                popup.beginFocusPrime()
            })
        }
        if (value.state === "Recording" || value.state === "Working" || value.state === "Confirm" || value.state === "Choose" || value.state === "Correction" || value.state === "TextEntry" || value.state === "Loading" || value.state === "WindowList") {
            dismissTimer.stop()
        } else if (popup.open && !manual && !dismissTimer.running) {
            dismissTimer.interval = value.state === "Error" ? 6000 : 2500
            dismissTimer.start()
        }
    }

    SystemClock { id: clock; precision: SystemClock.Seconds }
    Timer { id: dismissTimer; interval: 2500; onTriggered: root.close() }
    onAliveChanged: if (!alive && popup.open && !manual) dismissTimer.restart()
    // File notifications can be missed when the runtime atomically replaces
    // its JSON status file.  Polling is a cheap backstop and keeps overlays in
    // sync even after a shell/plugin reload.
    Timer {
        interval: 400
        running: true
        repeat: true
        onTriggered: statusFile.reload()
    }
    FileView {
        id: statusFile
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
    PanelWindow {
        id: writtenPanel
        objectName: "writtenPanel"
        screen: button.QsWindow.window ? button.QsWindow.window.screen : null
        visible: root.writtenOpen
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        color: "transparent"
        WlrLayershell.namespace: "skipper-written-command"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: root.writtenOpen ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        onVisibleChanged: if (visible) Qt.callLater(function() { writtenWords.forceActiveFocus() })
        // No timer, outside-click dismissal, bar coordinator, or focus-loss handler.
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(600, parent.width - 48)
            height: writtenContent.implicitHeight + 40
            color: Color.background
            border.color: Color.accent
            border.width: 2
            radius: 12
            Column {
                id: writtenContent
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 20 }
                spacing: 12
                Text {
                    text: "Type a command"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    font.bold: true
                }
                TextField {
                    id: writtenWords
                    objectName: "writtenWords"
                    width: parent.width
                    placeholderText: "e.g. tile this window and the browser"
                    maximumLength: 2000
                    onTextChanged: root.historySelection = text.trim() && CommandSearch.search(root.status.written_entry ? (root.status.written_entry.history || []) : [], text).length ? 0 : -1
                    onAccepted: root.submitWritten()
                    Keys.onDownPressed: root.selectHistory(1)
                    Keys.onUpPressed: {
                        if (root.historySelection < 0) root.historySelection = root.historyMatches.length - 1
                        else root.selectHistory(-1)
                    }
                    Keys.onTabPressed: root.recallHistory()
                    Keys.onPressed: function(event) {
                        if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                            root.historySelection = -1
                            root.submitWritten()
                            event.accepted = true
                        }
                    }
                    Keys.onEscapePressed: {
                        root.writtenOpen = false
                        root.action("cancel", root.writtenToken)
                    }
                }
                Repeater {
                    model: root.historyMatches
                    delegate: Rectangle {
                        required property string modelData
                        required property int index
                        width: writtenContent.width
                        height: 34
                        radius: 5
                        color: root.historySelection === index ? Color.accent : "transparent"
                        Text {
                            anchors { fill: parent; margins: 7 }
                            text: modelData
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: root.historySelection === index ? Color.background : Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.font.body
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: { root.historySelection = index; root.recallHistory() }
                        }
                    }
                }
                Text {
                    width: parent.width
                    text: root.status.written_entry && root.status.written_entry.error
                        ? root.status.written_entry.error : "↑↓ history · Tab to edit · Enter to run selection · Ctrl+Enter to run exactly what you typed · Esc to cancel"
                    textFormat: Text.PlainText
                    color: Color.muted
                    wrapMode: Text.Wrap
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                }
            }
        }
    }
    KeyboardPanel {
        id: popup
        anchorItem: button
        bar: root.bar
        owner: root
        // Use the shell's anchored keyboard dropdown; it reserves no workspace.
        focusTarget: root.state === "Correction" ? correctionWords : null
        WlrLayershell.keyboardFocus: open && root.state === "Correction"
            ? (focusPrimed ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.Exclusive)
            : WlrKeyboardFocus.None
        // Do not leave a fading result window over the app after execution.
        visible: open
        centerOnBar: root.state === "WindowList"
        contentWidth: fittedContentWidth(root.state === "WindowList" ? Style.space(680) : Style.space(440))
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
                        text: root.state === "WindowList" ? "Open windows" : "Skipper · " + root.state
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Button {
                        id: hideButton
                        text: root.state === "WindowList" ? "Close" : "×"
                        onClicked: root.state === "WindowList" ? root.action("dismiss-window-list") : root.close()
                    }
                }
                Rectangle {
                    width: parent.width
                    visible: root.status.input_source !== "written" && root.state !== "WindowList"
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
                    visible: root.state !== "WindowList"
                    text: root.status.transcript || (root.state === "TextEntry" ? "Written command" : root.state === "Recording" ? "Listening…" : "Hold Super + R to speak.")
                    textFormat: Text.PlainText
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    wrapMode: Text.Wrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                }
                Rectangle { width: parent.width; visible: root.state !== "WindowList"; height: visible ? 1 : 0; color: Qt.alpha(Color.foreground, 0.12) }
                Text {
                    width: parent.width
                    visible: root.state !== "WindowList"
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
                    visible: !!root.status.intent && root.state !== "WindowList"
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
                    visible: root.state !== "WindowList"
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
                    visible: root.state === "WindowList"
                    width: parent.width
                    spacing: Style.space(8)
                    Text {
                        width: parent.width
                        text: "Choose a window to focus"
                        color: Color.muted
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body * 0.9
                    }
                    Repeater {
                        model: root.status.window_list || []
                        Rectangle {
                            required property var modelData
                            width: parent.width
                            height: windowDetails.implicitHeight + Style.space(24)
                            radius: Style.space(8)
                            color: listedWindowMouse.containsMouse
                                ? Qt.alpha(Color.accent, 0.22) : Qt.alpha(Color.foreground, 0.07)
                            border.width: 1
                            border.color: listedWindowMouse.containsMouse
                                ? Qt.alpha(Color.accent, 0.8) : Qt.alpha(Color.foreground, 0.10)
                            Column {
                                id: windowDetails
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: Style.space(12) }
                                spacing: Style.space(4)
                                Text {
                                    width: parent.width
                                    text: modelData.title
                                    textFormat: Text.PlainText
                                    color: Color.foreground
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.body * 1.05
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: "Workspace " + modelData.workspace + "  ·  " + modelData.app
                                    textFormat: Text.PlainText
                                    color: Color.muted
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.body * 0.85
                                    elide: Text.ElideRight
                                }
                            }
                            MouseArea {
                                id: listedWindowMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.action("focus-listed-window", modelData.address)
                            }
                        }
                    }
                }
                Column {
                    visible: root.state === "Correction" && !!root.status.correction
                    width: parent.width
                    spacing: Style.space(8)
                    TextField {
                        id: correctionWords
                        objectName: "correctionWords"
                        width: parent.width
                        placeholderText: "Type the command you meant…"
                        maximumLength: 2000
                        onAccepted: root.submitCorrection("preview")
                    }
                    Text {
                        width: parent.width
                        text: root.status.correction && root.status.correction.error
                            ? root.status.correction.error
                            : root.correctionMatches ? "Intended action: " + root.status.correction.preview.label
                            : "Check the meaning, then save this correction for next time."
                        textFormat: Text.PlainText
                        color: Color.foreground
                        wrapMode: Text.Wrap
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                    }
                    Row {
                        spacing: Style.space(8)
                        Button { text: "Check meaning"; onClicked: root.submitCorrection("preview") }
                        Button { objectName: "saveCorrection"; text: "Save"; enabled: root.correctionMatches; onClicked: root.submitCorrection("save") }
                        Button { text: "Cancel"; bordered: true; onClicked: root.action("cancel", root.status.correction.token) }
                    }
                }
                Column {
                    visible: root.state === "Choose" && !!root.status.clarification
                    width: parent.width
                    spacing: Style.space(8)
                    Repeater {
                        model: root.status.clarification ? root.status.clarification.choices : []
                        Button {
                            required property var modelData
                            width: parent.width
                            text: modelData.label
                            onClicked: root.action("choose-window", modelData.token)
                        }
                    }
                    Button { text: "Cancel"; bordered: true; onClicked: root.action("cancel", "") }
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
                    visible: root.state !== "WindowList"
                    spacing: Style.space(8)
                    Button {
                        text: "History"
                        onClicked: {
                            var launcher = root.setting("explorerLauncher", root.pluginRoot + "/launch-explorer.sh")
                            if (launcher) Quickshell.execDetached([launcher, "--history"])
                            root.close()
                        }
                    }
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
