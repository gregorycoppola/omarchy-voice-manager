import "CommandSearch.js" as CommandSearch
import "CommandLevels.js" as CommandLevels
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
    readonly property bool websiteEntry: !!status.written_entry && status.written_entry.kind === "website"
    readonly property bool urlEntry: websiteEntry || (!!status.written_entry && status.written_entry.kind === "url")
    property string editingWebsiteId: ""
    property int websiteSelection: 0
    onWebsiteSelectionChanged: Qt.callLater(function() {
        var row = websiteRepeater.itemAt(websiteSelection)
        if (!row) return
        if (row.y < websiteFlick.contentY) websiteFlick.contentY = row.y
        else if (row.y + row.height > websiteFlick.contentY + websiteFlick.height)
            websiteFlick.contentY = row.y + row.height - websiteFlick.height
    })
    readonly property bool choosingBrowser: websiteEntry && !!status.written_entry.needs_browser
    readonly property bool existingBrowser: websiteEntry && status.written_entry.mode === "existing"
    property bool websiteTransitionPending: false
    property var websiteReturnState: null
    function beginWebsite(mode, remaining) {
        if (websiteTransitionPending) return
        if (queuedCommands.length) {
            pickerHint = "Run the queued steps before opening a website."
            return
        }
        websiteReturnState = {token: writtenToken, path: argumentPath.slice(),
            stack: argumentBackstack.slice(), text: writtenWords.text}
        websiteTransitionPending = true
        root.action("begin-website", JSON.stringify({token: writtenToken, mode: mode,
            text: writtenWords.text, initial_text: remaining || ""}))
    }
    readonly property var websiteMatches: {
        if (!websiteEntry) return []
        var query = writtenWords.text.trim().toLowerCase()
        if (choosingBrowser) return (status.written_entry.browser_choices || []).filter(function(row) {
            return !query || row.name.toLowerCase().indexOf(query) >= 0 || row.source.toLowerCase().indexOf(query) >= 0
        }).slice(0, 10)
        var saved = status.written_entry.sites || []
        var visited = (status.written_entry.most_visited || []).map(function(site) {
            var bookmark = saved.filter(function(row) { return row.url === site.url })[0]
            return {id: bookmark ? bookmark.id : site.id, name: site.name, url: site.url,
                saved: !!bookmark, source: site.visit_count + " visits"}
        })
        return visited.filter(function(site) {
            return !query || site.name.toLowerCase().indexOf(query) >= 0 || site.url.toLowerCase().indexOf(query) >= 0
        }).slice(0, 10)
    }
    function openWebsite(url) {
        writtenOpen = false
        root.action("submit-written", JSON.stringify({token: status.written_entry.token, text: url}))
    }
    function manageWebsite(operation, id) {
        root.action("manage-website", JSON.stringify({token: status.written_entry.token,
            operation: operation, id: id || null, name: websiteName.text, url: writtenWords.text}))
    }
    property var queuedCommands: []
    property int historySelection: -1
    property var argumentPath: []
    property var argumentBackstack: []
    property bool commandComplete: false
    property string acceptedControl: ""
    property bool controlSelectionLost: false
    readonly property bool controlLevel: !!argumentLevel.controlProvider
    readonly property var controlState: status.written_entry ? (status.written_entry.controls || {}) : ({})
    onControlLevelChanged: Qt.callLater(function() { root.loadControls() })
    function loadControls() {
        if (writtenOpen && controlLevel && !commandComplete) root.action("load-controls", writtenToken)
    }
    Timer {
        interval: 3000; repeat: true
        running: root.writtenOpen && root.controlLevel && !root.commandComplete
        onTriggered: root.loadControls()
    }
    property string acceptedFile: ""
    readonly property bool fileLevel: !!argumentLevel.fileProvider
    readonly property var fileState: status.written_entry ? (status.written_entry.files || {}) : ({})
    readonly property string fileQuery: {
        var text = writtenWords.text.trim()
        if (/^open\s+file(?:\s|$)/i.test(text)) return text.replace(/^open\s+file\s*/i, "").trim()
        if (!argumentPath.length && CommandLevels.subsequence("open file", text)) return ""
        return text
    }
    onFileLevelChanged: {
        if (fileLevel) fileSearchDelay.restart()
        else fileSearchDelay.stop()
    }
    onFileQueryChanged: {
        if (fileLevel && !commandComplete) fileSearchDelay.restart()
    }
    Timer {
        id: fileSearchDelay
        interval: 180
        onTriggered: {
            if (!root.writtenOpen || !root.fileLevel || root.commandComplete) return
            root.action("search-files", JSON.stringify({token: root.writtenToken, query: root.fileQuery}))
        }
    }
    property var acceptedAudio: null
    property bool audioSelectionLost: false
    readonly property string audioDirection: argumentLevel.audioDirection || ""
    readonly property var audioState: status.written_entry && status.written_entry.audio
        ? (status.written_entry.audio[audioDirection] || {}) : ({})
    onAudioDirectionChanged: Qt.callLater(function() { root.loadAudio() })
    function loadAudio() {
        if (!writtenOpen || !audioDirection || commandComplete || !status.written_entry) return
        root.action("load-audio", JSON.stringify({token: writtenToken, direction: audioDirection}))
    }
    Timer {
        interval: 3000; repeat: true
        running: root.writtenOpen && !!root.audioDirection && !root.commandComplete
        onTriggered: root.loadAudio()
    }
    property string pickerHint: ""
    property var commandTree: []
    property string commandCatalogKey: ""
    property bool autoSuppressed: false
    property var matchCheckpoints: []
    readonly property var prefixPreview: CommandLevels.rememberedPreview(commandTree, argumentPath,
        writtenWords.text, autoSuppressed || urlEntry || commandComplete, matchCheckpoints)
    readonly property var argumentLevel: prefixPreview.level
    readonly property string argumentPrompt: fileLevel ? (fileQuery ? "SEARCH FILENAMES · HOME FOLDER" : "RECENTLY OPENED FILES")
        : audioDirection ? (audioDirection === "output" ? "CHOOSE AN AUDIO OUTPUT" : "CHOOSE A MICROPHONE")
        : argumentLevel.argumentPrompt ? argumentLevel.argumentPrompt
        : !prefixPreview.path.length ? "CHOOSE AN ACTION"
        : /^move\b/i.test(argumentLevel.prefix || "") && /\bto$/i.test(argumentLevel.prefix || "") ? "CHOOSE A WORKSPACE OR MONITOR"
        : /^(move|close|minimize|maximize|focus|show)$/i.test(argumentLevel.prefix || "") ? "CHOOSE A WINDOW"
        : "CHOOSE AN OPTION"
    readonly property var levelOptions: prefixPreview.rows
    onPrefixPreviewChanged: Qt.callLater(function() { root.expandWebsitePrefix() })
    function expandWebsitePrefix() {
        if (!writtenOpen || urlEntry || commandComplete || autoSuppressed || websiteTransitionPending) return
        if (prefixPreview.portal) beginWebsite(prefixPreview.portal.websiteMode, prefixPreview.portalQuery)
    }
    readonly property var pickerRows: {
        if (urlEntry || commandComplete) return []
        if (fileLevel && (fileState.loading || fileState.query !== fileQuery)) return []
        var query = prefixPreview.query
        // Browsing Tile/List retains the category order, including abbreviated verbs.
        if (/^(tile|list)$/.test(argumentLevel.prefix || "")
                && CommandLevels.subsequence(argumentLevel.prefix, query)) query = ""
        var ranked = CommandSearch.rank(fileLevel ? fileQuery : query, levelOptions, [],
            status.written_entry ? status.written_entry.counts : {})
        if (!ranked.length && levelOptions.length) ranked = levelOptions.map(function(row, i) {
            return {index: i, text: row.text}
        })
        return ranked.slice(0, 10).map(function(row) {
            var option = levelOptions[row.index]
            // Full commands show and accept the supported phrase that matched.
            // Argument labels and expandable branches retain their stage wording.
            return option.matchWording
                ? Object.assign({}, option, {text: row.text, value: row.text}) : option
        })
    }
    readonly property var historyMatches: pickerRows.map(function(row) { return row.text })
    function pickerVerb(text) {
        return String(text || "").replace(/…/g, "").trim().toLowerCase().split(/\s+/)[0]
    }
    function pickerIcon(text) {
        var verb = pickerVerb(text)
        var icons = {open: "↗", minimize: "−", maximize: "□", move: "⇄", close: "×",
            list: "☷", tile: "▥", switch: "⇆", focus: "⌖", hide: "−", show: "▣",
            bring: "↗", launch: "↗", mute: "♪", volume: "♪", lock: "◇"}
        return icons[verb] || "›"
    }
    function pickerDescription(row) {
        if (!row) return ""
        if (row.description) return row.description
        if (row.controlProvider) return row.prefixWords === "connect" || row.prefixWords === "disconnect"
            ? "Paired Bluetooth devices" : "Night light, Wi-Fi and Bluetooth · current state shown"
        if (row.fileProvider) return "Search filenames in your home folder"
        if (row.audioDirection) return "Choose the default " + (row.audioDirection === "input" ? "microphone" : "audio output")
        var verb = pickerVerb(row.text)
        if (row.verbGroup) {
            var descriptions = {open: "Applications, terminals and websites", minimize: "Put windows out of the way",
                maximize: "Give a window room to work", move: "Windows, workspaces and monitors",
                close: "Close a selected window", list: "See what is open", tile: "Arrange windows together",
                switch: "Change windows or workspaces", focus: "Jump to an open window",
                hide: "Clear space without closing apps", show: "Bring a window to this workspace",
                bring: "Bring an application into view", launch: "Launch an application"}
            return descriptions[verb] || "Explore available commands"
        }
        if (row.websiteMode) return "Choose a website and where it opens"
        if (row.children) return "Choose the next part of your command"
        return "Ready to run · Enter to execute"
    }
    readonly property bool canQueueCommand: !urlEntry && !audioDirection && !acceptedAudio && !fileLevel && !acceptedFile && !controlLevel && !acceptedControl && queuedCommands.length < 20
        && (commandComplete || (pickerRows.length > 0
            && (!pickerRows[Math.min(pickerRows.length - 1, Math.max(0, historySelection))].children
                || !!pickerRows[Math.min(pickerRows.length - 1, Math.max(0, historySelection))].optionalArguments)
            && !pickerRows[Math.min(pickerRows.length - 1, Math.max(0, historySelection))].audioChoice
            && !pickerRows[Math.min(pickerRows.length - 1, Math.max(0, historySelection))].fileChoice
            && !pickerRows[Math.min(pickerRows.length - 1, Math.max(0, historySelection))].controlChoice
            && !pickerRows[Math.min(pickerRows.length - 1, Math.max(0, historySelection))].websiteMode))
    onHistorySelectionChanged: Qt.callLater(function() {
        var row = commandRepeater.itemAt(historySelection)
        if (!row) return
        if (row.y < commandFlick.contentY) commandFlick.contentY = row.y
        else if (row.y + row.height > commandFlick.contentY + commandFlick.height)
            commandFlick.contentY = row.y + row.height - commandFlick.height
    })
    function selectHistory(delta) {
        controlSelectionLost = false
        audioSelectionLost = false
        if (websiteEntry) {
            if (websiteMatches.length) websiteSelection = (websiteSelection + delta + websiteMatches.length) % websiteMatches.length
            return
        }
        if (!historyMatches.length) return
        historySelection = (historySelection + delta + historyMatches.length) % historyMatches.length
    }
    function advanceArgument() {
        audioSelectionLost = false
        if (websiteEntry) {
            if (choosingBrowser) { submitWritten(); return }
            var site = websiteMatches[Math.min(websiteSelection, websiteMatches.length - 1)]
            if (site) writtenWords.text = site.url
            pickerHint = "Press Enter to open this website."
            writtenWords.forceActiveFocus()
            return
        }
        if (commandComplete || !pickerRows.length) return
        var index = historySelection >= 0 ? historySelection : 0
        var row = pickerRows[index]
        if (!row) return
        if (row.unavailable) { pickerHint = "This control is currently unavailable."; return }
        controlSelectionLost = false
        var current = prefixPreview
        matchCheckpoints = []
        if (row.websiteMode) {
            beginWebsite(row.websiteMode, CommandLevels.words(current.query).slice(CommandLevels.consumed(row, current.query)).join(' '))
            return
        }
        argumentBackstack = argumentBackstack.concat(current.frames, [{
            path: current.path.slice(), text: current.query, selection: index}])
        pickerHint = ""
        autoSuppressed = false
        if (row.children) {
            argumentPath = current.path.concat([row.id])
            if (row.fileProvider || row.optionalArguments || row.clearInput) writtenWords.text = ""
            // Keep the full query visible when selecting a branch.
            historySelection = 0
        } else {
            argumentPath = current.path
            acceptedAudio = row.audioChoice || null
            acceptedFile = row.fileChoice || ""
            acceptedControl = row.controlChoice || ""
            commandComplete = true
            writtenWords.text = row.value
            commandComplete = true
            historySelection = -1
        }
        writtenWords.forceActiveFocus()
    }
    function previousArgument() {
        acceptedControl = ""
        controlSelectionLost = false
        acceptedFile = ""
        acceptedAudio = null
        audioSelectionLost = false
        if (websiteEntry) { root.action("website-back", writtenToken); return }
        var history = argumentBackstack.concat(prefixPreview.frames)
        if (!history.length) return
        var saved = history[history.length - 1]
        matchCheckpoints = []
        argumentBackstack = history.slice(0, -1)
        autoSuppressed = true
        commandComplete = false
        argumentPath = saved.path
        writtenWords.text = saved.text
        historySelection = saved.selection
        pickerHint = ""
        writtenWords.forceActiveFocus()
    }
    function recallHistory() {
        controlSelectionLost = false
        audioSelectionLost = false
        // Clicking only selects. Tab is the explicit level transition.
        writtenWords.forceActiveFocus()
    }
    function selectedCommand() {
        if (commandComplete) return writtenWords.text.trim()
        var row = pickerRows[historySelection >= 0 ? historySelection : 0]
        if (row && (!row.children || row.optionalArguments) && !row.websiteMode) return row.value
        if (row || argumentPath.length) {
            pickerHint = "Press Tab to choose the next argument."
            return ""
        }
        return writtenWords.text.trim()
    }
    function resetArguments() {
        acceptedControl = ""
        controlSelectionLost = false
        acceptedFile = ""
        acceptedAudio = null
        audioSelectionLost = false
        matchCheckpoints = []
        argumentPath = []
        argumentBackstack = []
        commandComplete = false
        autoSuppressed = false
        pickerHint = ""
    }
    function queueCommand() {
        var text = selectedCommand()
        if (!text || queuedCommands.length >= 20) return
        queuedCommands = queuedCommands.concat([text])
        resetArguments()
        writtenWords.text = ""
        historySelection = -1
        writtenWords.forceActiveFocus()
    }
    function removeQueued(index) {
        var next = queuedCommands.slice()
        next.splice(index, 1)
        queuedCommands = next
        writtenWords.forceActiveFocus()
    }
    property string answeredConfirmation: ""
    readonly property bool confirmationOpen: root.state === "Confirm" && !!status.confirmation
        && status.confirmation.token !== answeredConfirmation
        && (!status.monitor || status.monitor === screenName)
    function answerConfirmation(yes) {
        if (!confirmationOpen) return
        var token = status.confirmation.token
        answeredConfirmation = token
        root.action(yes ? "confirm" : "cancel", token)
    }
    readonly property bool correctionMatches: !!status.correction && !!status.correction.preview
        && status.correction.preview.said === correctionWords.text.trim()
        && status.correction.preview.meant === correctionWords.text.trim()
    readonly property string barText: recentIntent ? recentIntent + " · Skipper" : "Skipper"
    readonly property bool alive: (clock.date.getTime() / 1000 - (status.updated || 0)) < 8
    readonly property string state: alive ? (status.state || "Stopped") : "Stopped"
    readonly property bool working: state === "Working" || state === "Loading"
    readonly property bool opened: popup.open
    readonly property string screenName: button.QsWindow.window && button.QsWindow.window.screen
                                        ? button.QsWindow.window.screen.name : ""
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function snapshot() { return {opened: popup.open, visible: popup.visible, state: state, barText: barText, screen: screenName, writtenOpen: writtenOpen, writtenFocused: writtenWords.activeFocus, argumentPath: argumentPath, choices: historyMatches, commandComplete: commandComplete, writtenText: writtenWords.text} }
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
        if (websiteEntry) {
            var address = writtenWords.text.trim()
            if (websiteMatches.length && (choosingBrowser || !address || !/[.:/]/.test(address)))
                address = websiteMatches[Math.min(websiteSelection, websiteMatches.length - 1)].url
            openWebsite(address)
            return
        }
        var selected = pickerRows[historySelection >= 0 ? historySelection : 0]
        var control = commandComplete ? acceptedControl : (selected ? selected.controlChoice : "")
        if (control) {
            if (controlSelectionLost || (!commandComplete && selected.unavailable)) { pickerHint = "Choose an available control again."; return }
            if (queuedCommands.length) { pickerHint = "Run queued steps before changing system controls."; return }
            writtenOpen = false
            root.action("submit-written", JSON.stringify({token: writtenToken, control: control}))
            return
        }
        if (controlLevel && !selected) { pickerHint = "Choose an available system control."; return }
        var file = commandComplete ? acceptedFile : (selected ? selected.fileChoice : "")
        if (file) {
            if (queuedCommands.length) { pickerHint = "Run the queued steps before opening a file."; return }
            writtenOpen = false
            root.action("submit-written", JSON.stringify({token: writtenToken, file: file}))
            return
        }
        if (fileLevel && (!selected || !selected.children)) {
            pickerHint = "Choose a file, or type a filename to narrow the list."
            return
        }
        var audio = commandComplete ? acceptedAudio : (selected ? selected.audioChoice : null)
        if (audio) {
            if (audioSelectionLost) { pickerHint = "Choose a device again after the list changed."; return }
            if (queuedCommands.length) { pickerHint = "Run the queued steps before switching audio devices."; return }
            writtenOpen = false
            root.action("submit-written", JSON.stringify({token: writtenToken, audio: audio}))
            return
        }
        if (audioDirection && (!selected || !selected.children)) {
            pickerHint = "Choose an available audio device."
            return
        }
        if (!urlEntry && !commandComplete && selected && selected.websiteMode) {
            beginWebsite(selected.websiteMode, prefixPreview.portalQuery || "")
            return
        }
        if (!urlEntry && !commandComplete && selected && selected.children && !selected.optionalArguments) {
            advanceArgument()
            return
        }
        var command = urlEntry ? writtenWords.text.trim() : selectedCommand()
        if (!urlEntry && !command && (argumentPath.length || writtenWords.text.trim() || pickerHint)) return
        if (!command && !queuedCommands.length) return
        writtenOpen = false
        var steps = queuedCommands.slice()
        if (command) steps.push(command)
        var request = {token: status.written_entry.token, text: command}
        if (queuedCommands.length) request = {token: status.written_entry.token, steps: steps}
        root.action("submit-written", JSON.stringify(request))
    }
    function readStatus(value) {
        var entry = value.written_entry || {}
        var selectedAudioRow = pickerRows[historySelection >= 0 ? historySelection : 0]
        var selectedAudioId = selectedAudioRow && selectedAudioRow.audioChoice ? selectedAudioRow.audioChoice.id : ""
        var selectedControlId = selectedAudioRow && selectedAudioRow.controlChoice ? selectedAudioRow.controlChoice : ""
        var sources = [entry.suggestions || [], entry.dynamic_suggestions || [], entry.audio || {}, entry.files || {}, entry.controls || {}]
        var key = JSON.stringify(sources)
        if (key !== commandCatalogKey) {
            commandCatalogKey = key
            commandTree = CommandLevels.build(sources[0], sources[1], sources[2], sources[3], sources[4])
        }
        var previousCompletion = status.completed_at || 0
        var previousState = status.state || "Stopped"
        var event = String(value.session || "") + ":" + String(value.panel_epoch || 0)
        var newEvent = event !== seenEvent
        seenEvent = event
        if (status.written_entry && value.written_entry &&
            JSON.stringify(status.written_entry.dynamic_suggestions) !== JSON.stringify(value.written_entry.dynamic_suggestions))
            historySelection = -1
        status = value
        if (selectedControlId && controlLevel) {
            var controlIndex = pickerRows.findIndex(function(row) { return row.controlChoice === selectedControlId })
            historySelection = controlIndex
            if (controlIndex < 0) { controlSelectionLost = true; pickerHint = "The selected device disappeared. Choose another option." }
        }
        if (selectedAudioId && audioDirection) {
            var retained = pickerRows.findIndex(function(row) { return row.audioChoice && row.audioChoice.id === selectedAudioId })
            historySelection = retained
            if (retained < 0) {
                audioSelectionLost = true
                pickerHint = "The selected device disconnected. Choose another device."
            }
        }
        if (!value.written_entry) { writtenOpen = false; websiteTransitionPending = false }
        if (value.correction && value.correction.token !== correctionToken) {
            correctionToken = value.correction.token
            correctionWords.text = ""
        }
        if (value.written_entry && value.written_entry.token !== writtenToken) {
            historySelection = -1
            websiteTransitionPending = false
            writtenToken = value.written_entry.token
            queuedCommands = []
            resetArguments()
            websiteSelection = 0
            editingWebsiteId = ""
            websiteName.text = ""
            writtenWords.text = value.written_entry.text || ""
            if (websiteReturnState && writtenToken === websiteReturnState.token) {
                argumentPath = websiteReturnState.path
                argumentBackstack = websiteReturnState.stack
                writtenWords.text = websiteReturnState.text
                autoSuppressed = true
                websiteReturnState = null
            }
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
        if (value.state === "WindowList" || value.state === "Choose") {
            popup.open = false
            dismissTimer.stop()
            if (newEvent) selectionPanel.focusDefault()
            return
        }
        if (value.state === "Confirm" && value.confirmation) {
            popup.open = false
            dismissTimer.stop()
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
        if (value.state === "Working" || value.state === "Confirm" || value.state === "Choose" || value.state === "Correction" || value.state === "TextEntry" || value.state === "Loading" || value.state === "WindowList") {
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
        activeColor: root.state === "Error" ? Color.urgent : foreground
        tooltipText: "Super + R to choose a command · " + root.state
        onPressed: function(b) { root.togglePanel() }
    }
    PanelWindow {
        id: confirmationPanel
        objectName: "confirmationPanel"
        screen: button.QsWindow.window ? button.QsWindow.window.screen : null
        visible: root.confirmationOpen
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        color: "transparent"
        WlrLayershell.namespace: "skipper-confirmation"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        onVisibleChanged: if (visible) Qt.callLater(function() { confirmationCard.forceActiveFocus() })
        Rectangle {
            id: confirmationCard
            objectName: "confirmationCard"
            anchors.centerIn: parent
            width: Math.min(600, parent.width - 48)
            height: confirmationContent.implicitHeight + 48
            radius: 12
            color: Color.background
            border.color: Color.accent
            border.width: 2
            focus: true
            Keys.onPressed: function(event) {
                if (event.isAutoRepeat) { event.accepted = true; return }
                if (event.key === Qt.Key_Y || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    root.answerConfirmation(true); event.accepted = true
                } else if (event.key === Qt.Key_N || event.key === Qt.Key_Escape) {
                    root.answerConfirmation(false); event.accepted = true
                }
            }
            Column {
                id: confirmationContent
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
                spacing: 18
                Text {
                    width: parent.width
                    text: root.status.confirmation ? root.status.confirmation.title : ""
                    textFormat: Text.PlainText
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body * 1.5
                    font.bold: true
                    wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width
                    text: root.status.confirmation ? root.status.confirmation.detail : ""
                    textFormat: Text.PlainText
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width
                    text: root.status.message || ""
                    textFormat: Text.PlainText
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    wrapMode: Text.Wrap
                }
                Row {
                    spacing: 16
                    Button { objectName: "confirmationYes"; text: "Yes  ·  Enter / Y"; width: (confirmationContent.width - 16) / 2; height: 56; onClicked: root.answerConfirmation(true) }
                    Button { objectName: "confirmationNo"; text: "No  ·  Escape / N"; width: (confirmationContent.width - 16) / 2; height: 56; bordered: true; onClicked: root.answerConfirmation(false) }
                }
                Text {
                    width: parent.width
                    text: "Choose Yes or No to continue."
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body * 0.85
                    wrapMode: Text.Wrap
                }
            }
        }
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
            width: Math.min(760, parent.width - 48)
            height: Math.min(writtenContent.implicitHeight + 40, parent.height - 64)
            color: Color.background
            border.color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.35)
            border.width: 1
            radius: 16
            Flickable {
                anchors { fill: parent; margins: 20 }
                contentHeight: writtenContent.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
            Column {
                id: writtenContent
                width: parent.width
                spacing: 14
                Row {
                    width: parent.width
                    height: 24
                    spacing: 10
                    Text { text: "⌘"; color: Color.accent; font.pixelSize: 22; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: "SKIPPER"
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Math.max(12, Style.font.body)
                        font.letterSpacing: 1.2
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Item { width: Math.max(0, parent.width - 285); height: 1 }
                    Text {
                        text: root.queuedCommands.length ? root.queuedCommands.length + " steps queued" : "Desktop commands"
                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                        font.family: Style.font.family
                        font.pixelSize: 12
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Flickable {
                    width: parent.width
                    height: Math.min(160, queuedColumn.implicitHeight)
                    contentHeight: queuedColumn.implicitHeight
                    clip: true
                    Column {
                        id: queuedColumn
                        width: parent.width
                        spacing: 6
                Repeater {
                    model: root.queuedCommands
                    delegate: Row {
                        required property string modelData
                        required property int index
                        width: writtenContent.width
                        spacing: 8
                        Text {
                            width: parent.width - 85
                            text: (index + 1) + ". " + modelData
                            textFormat: Text.PlainText
                            color: Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.font.body
                            elide: Text.ElideRight
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Button { text: "Remove"; onClicked: root.removeQueued(index) }
                    }
                }
                    }
                }
                TextField {
                    id: writtenWords
                    objectName: "writtenWords"
                    width: parent.width
                    height: 56
                    font.pixelSize: Math.max(22, Style.font.body * 1.5)
                    leftPadding: 15
                    rightPadding: 15
                    color: Color.foreground
                    placeholderTextColor: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.55)
                    background: Rectangle {
                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.035)
                        radius: 10
                        border.width: 1
                        border.color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.18)
                    }
                    placeholderText: root.fileLevel && !root.commandComplete ? "Search filenames…" : root.websiteEntry ? (root.choosingBrowser ? "Choose a Chrome/Chromium window…" : "Search most visited sites or enter an address…") : root.urlEntry ? "https://example.com" : root.argumentPath.length && !root.commandComplete ? "Choose an argument, then press Tab…" : root.queuedCommands.length ? "Next command… Enter runs the sequence" : "What would you like to do?"
                    maximumLength: 2000
                    onTextEdited: {
                        root.autoSuppressed = false
                        if (!root.urlEntry) {
                            if (root.commandComplete) root.resetArguments()
                            root.matchCheckpoints = root.prefixPreview.checkpoints
                        }
                        Qt.callLater(function() { root.expandWebsitePrefix() })
                    }
                    onTextChanged: {
                        root.websiteSelection = 0
                        root.pickerHint = ""
                        root.historySelection = root.historyMatches.length ? 0 : -1
                    }
                    onAccepted: root.submitWritten()
                    Keys.onDownPressed: root.selectHistory(1)
                    Keys.onUpPressed: {
                        if (!root.websiteEntry && root.historySelection < 0) root.historySelection = root.historyMatches.length - 1
                        else root.selectHistory(-1)
                    }
                    Keys.onTabPressed: function(event) {
                        if (root.urlEntry && !root.websiteEntry) { event.accepted = false; return }
                        if (!event.isAutoRepeat) root.advanceArgument()
                        event.accepted = true
                    }
                    Keys.onBacktabPressed: function(event) {
                        if (root.urlEntry && !root.websiteEntry) { event.accepted = false; return }
                        root.previousArgument()
                        event.accepted = true
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Backspace && !text && (root.argumentPath.length || root.prefixPreview.frames.length || root.websiteEntry)) {
                            root.previousArgument()
                            event.accepted = true
                            return
                        }
                        if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                            if (root.argumentPath.length && !root.commandComplete) {
                                root.pickerHint = "Complete the arguments with Tab first."
                                event.accepted = true
                                return
                            }
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
                Rectangle {
                    visible: !root.urlEntry && (root.prefixPreview.path.length > 0 || root.commandComplete)
                    width: parent.width
                    height: prefixText.implicitHeight + 18
                    radius: 7
                    color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.09)
                    Text {
                        id: prefixText
                        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                        text: root.commandComplete ? "Ready  ·  " + writtenWords.text : root.argumentLevel.prefix + "  ›"
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: Color.accent
                        font.family: Style.font.family
                        font.pixelSize: Math.max(13, Style.font.body)
                    }
                }
                Column {
                    visible: root.websiteEntry
                    width: parent.width
                    spacing: 10
                    TextField {
                        id: websiteName
                        visible: !root.choosingBrowser
                        width: parent.width
                        placeholderText: "Name for saved website (optional)"
                        maximumLength: 80
                        onAccepted: root.manageWebsite("save", root.editingWebsiteId)
                        Keys.onEscapePressed: { root.writtenOpen = false; root.action("cancel", root.writtenToken) }
                    }
                    Row {
                        spacing: 8
                        Button { text: "Back"; focusable: true; onClicked: root.previousArgument() }
                        Button { text: root.choosingBrowser ? "Choose browser" : "Open website"; focusable: true; onClicked: root.submitWritten() }
                        Button { text: root.editingWebsiteId ? "Save changes" : "Save website"; visible: !root.choosingBrowser; focusable: true; onClicked: root.manageWebsite("save", root.editingWebsiteId) }
                        Button {
                            text: "Clear"; focusable: true
                            onClicked: { root.editingWebsiteId = ""; websiteName.text = ""; writtenWords.text = ""; writtenWords.forceActiveFocus() }
                        }
                    }
                    Text {
                        text: root.choosingBrowser ? "Existing browser windows" : root.existingBrowser ? "Most visited websites → " + ((root.status.written_entry || {}).target_label || "Browser") : "Most visited websites"
                        width: parent.width
                        elide: Text.ElideRight
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                    }
                    Button {
                        text: "Refresh browser history"; visible: !root.choosingBrowser; focusable: true
                        enabled: !(root.status.written_entry || {}).history_loading
                        onClicked: root.manageWebsite("import_history", "")
                    }
                    Text {
                        width: parent.width
                        text: (root.status.written_entry || {}).history_loading ? "Reading browser history…"
                            : (root.status.written_entry || {}).history_message || ""
                        visible: text.length > 0
                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        wrapMode: Text.Wrap
                    }
                    Flickable {
                        width: parent.width
                        id: websiteFlick
                        height: Math.min(220, websiteRows.implicitHeight)
                        contentHeight: websiteRows.implicitHeight
                        clip: true
                        Column {
                            id: websiteRows
                            width: parent.width
                            spacing: 8
                            Repeater {
                                id: websiteRepeater
                                model: root.websiteMatches
                                delegate: Row {
                                    required property var modelData
                                    required property int index
                                    width: websiteRows.width
                                    spacing: 6
                                    Column {
                                        width: parent.width - siteButtons.width - 6
                                        Text {
                                            width: parent.width
                                            text: (index === root.websiteSelection ? "› " : "") + modelData.name + " · " + modelData.source
                                            font.bold: index === root.websiteSelection
                                            textFormat: Text.PlainText
                                            color: Color.foreground
                                            font.family: Style.font.family
                                            font.pixelSize: Style.font.body
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            width: parent.width
                                            text: modelData.browserChoice ? "Tab to select this window" : modelData.url
                                            textFormat: Text.PlainText
                                            color: Color.foreground
                                            font.family: Style.font.family
                                            font.pixelSize: Style.font.body * 0.9
                                            elide: Text.ElideRight
                                        }
                                    }
                                    Row {
                                        id: siteButtons
                                        spacing: 4
                                        Button { text: root.choosingBrowser ? "Choose" : "Open"; focusable: true; onClicked: root.openWebsite(modelData.url) }
                                        Button {
                                            text: modelData.saved ? "Edit" : "Save"; visible: !root.choosingBrowser; focusable: true
                                            onClicked: {
                                                root.editingWebsiteId = modelData.saved ? modelData.id : ""
                                                writtenWords.text = modelData.url
                                                websiteName.text = modelData.name
                                                writtenWords.forceActiveFocus()
                                            }
                                        }
                                        Button { text: "Remove"; visible: modelData.saved; focusable: true; onClicked: root.manageWebsite("remove", modelData.id) }
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        visible: !root.websiteMatches.length
                        text: root.choosingBrowser ? "No matching Chrome/Chromium window. Go back to use a new browser." : "No matching visited sites. Enter a web address to open it."
                        width: parent.width
                        wrapMode: Text.Wrap
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                    }
                    Keys.onEscapePressed: { root.writtenOpen = false; root.action("cancel", root.writtenToken) }
                }
                Text {
                    visible: !root.urlEntry && root.historyMatches.length > 0
                    text: root.argumentPrompt
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                    font.family: Style.font.family
                    font.pixelSize: 11
                    font.letterSpacing: 1.2
                    leftPadding: 10
                }
                Flickable {
                    id: commandFlick
                    visible: !root.urlEntry && root.historyMatches.length > 0
                    width: parent.width
                    height: Math.min(commandColumn.implicitHeight, 348, writtenPanel.height * 0.43)
                    contentHeight: commandColumn.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: commandColumn
                        width: parent.width
                        spacing: 4
                        Repeater {
                            id: commandRepeater
                            model: root.pickerRows
                            delegate: Rectangle {
                                required property var modelData
                                required property int index
                                readonly property bool selected: root.historySelection === index
                                width: commandColumn.width
                                height: 54
                                radius: 9
                                color: selected ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.16) : "transparent"
                                border.width: 1
                                border.color: selected ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.45) : "transparent"
                                Rectangle {
                                    id: rowIcon
                                    anchors { left: parent.left; leftMargin: 11; verticalCenter: parent.verticalCenter }
                                    width: 32; height: 32; radius: 7
                                    color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.09)
                                    Text { anchors.centerIn: parent; text: root.pickerIcon(modelData.text); color: Color.accent; font.pixelSize: 20 }
                                }
                                Column {
                                    anchors { left: rowIcon.right; leftMargin: 13; right: rowTail.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                    spacing: 4
                                    Text {
                                        width: parent.width
                                        text: modelData.text.replace(/…$/, "")
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        color: Color.foreground
                                        font.family: Style.font.family
                                        font.pixelSize: Math.max(14, Style.font.body)
                                        font.capitalization: modelData.verbGroup ? Font.Capitalize : Font.MixedCase
                                        font.weight: Font.Medium
                                    }
                                    Text {
                                        width: parent.width
                                        text: root.pickerDescription(modelData)
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                                        font.family: Style.font.family
                                        font.pixelSize: Math.max(11, Style.font.body * 0.88)
                                    }
                                }
                                Text {
                                    id: rowTail
                                    anchors { right: parent.right; rightMargin: 15; verticalCenter: parent.verticalCenter }
                                    text: modelData.children || modelData.websiteMode ? "›" : "↵"
                                    color: parent.selected ? Color.accent : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                                    font.pixelSize: 18
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: { root.historySelection = index; root.recallHistory() }
                                }
                            }
                        }
                    }
                }
                Text {
                    visible: !root.urlEntry && !root.commandComplete && !root.historyMatches.length
                    width: parent.width
                    text: root.controlLevel ? (root.controlState.loading || !root.controlState.rows ? "Loading system state…"
                        : root.controlState.error || "No matching controls or paired Bluetooth devices.")
                        : root.fileLevel ? (root.fileState.loading || root.fileState.query !== root.fileQuery ? "Searching filenames…"
                        : root.fileState.error || (root.fileQuery ? "No matching files in your home folder." : "No recent files available. Type a filename to search your home folder."))
                        : root.audioDirection ? (root.audioState.loading || !root.audioState.rows ? "Loading audio devices…"
                        : root.audioState.error || (root.audioState.rows.length ? "No matching audio devices." : "No available audio devices."))
                        : "No matching commands. Try a different word."
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                    font.family: Style.font.family
                    font.pixelSize: 13
                    wrapMode: Text.Wrap
                }
                Rectangle { width: parent.width; height: 1; color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.1) }
                Row {
                    visible: !root.urlEntry
                    width: parent.width
                    spacing: 10
                    Button { text: "Back"; visible: root.argumentBackstack.length > 0 || root.prefixPreview.frames.length > 0; onClicked: root.previousArgument() }
                    Button { text: "+ Add step"; visible: root.canQueueCommand; onClicked: root.queueCommand() }
                    Text {
                        text: root.commandComplete ? "Ready to run" : root.historyMatches.length + " choices"
                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                        font.family: Style.font.family
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Text {
                    width: parent.width
                    text: root.status.written_entry && root.status.written_entry.error
                        ? root.status.written_entry.error : root.websiteEntry ? (root.choosingBrowser ? "Tab to choose browser · Shift+Tab back · Esc to cancel" : "Tab to accept site · Enter to open · ↑↓ to choose · Shift+Tab back · Esc to cancel")
                        : root.urlEntry ? "Enter to open in your browser · Esc to cancel"
                        : root.pickerHint || (root.fileLevel && !root.commandComplete ? (root.fileState.limited ? (root.fileQuery ? "First 80 candidates · Narrow your filename search · Enter opens the selected file" : "Recent files · Type to search filenames · Enter opens the selected file") : "Tab accepts a file · Enter opens in its default app · Shift+Tab back") : root.commandComplete ? "Enter  Run command   ·   Shift+Tab  Back   ·   Esc  Close" : root.queuedCommands.length ? "↑↓  Choose   ·   Tab  Select   ·   Enter  Run sequence   ·   Esc  Close" : "↑↓  Choose   ·   Tab  More arguments / select   ·   Enter  Continue / run   ·   Esc  Close")
                    textFormat: Text.PlainText
                    color: root.status.written_entry && root.status.written_entry.error ? Color.accent : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.65)
                    wrapMode: Text.Wrap
                    font.family: Style.font.family
                    font.pixelSize: Math.max(11, Style.font.body * 0.88)
                }
            }
            }
        }
    }
    PanelWindow {
        id: selectionPanel
        objectName: "selectionPanel"
        screen: button.QsWindow.window ? button.QsWindow.window.screen : null
        visible: (root.state === "WindowList" || root.state === "Choose")
            && (!root.status.monitor || root.status.monitor === root.screenName)
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        color: "transparent"
        WlrLayershell.namespace: "skipper-selection"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        function focusDefault() {
            Qt.callLater(function() {
                if (!selectionPanel.visible) return
                var firstChoice = root.state === "Choose" ? selectionChoices.itemAt(0) : null
                if (firstChoice) firstChoice.forceActiveFocus()
                else selectionClose.forceActiveFocus()
            })
        }
        onVisibleChanged: if (visible) focusDefault()
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(680, parent.width - 48)
            height: Math.min(selectionContent.implicitHeight + 40, parent.height - 80)
            color: Color.background
            border.color: Color.accent
            border.width: 2
            radius: 12
            Flickable {
                id: selectionScroll
                anchors { fill: parent; margins: 20 }
                contentHeight: selectionContent.implicitHeight
                clip: true
                Column {
                    id: selectionContent
                    width: parent.width
                    spacing: 12
                    Keys.onEscapePressed: root.action(root.state === "WindowList" ? "dismiss-window-list" : "cancel", root.state === "WindowList" ? undefined : "")
                    Row {
                        width: parent.width
                        Text {
                            width: parent.width - selectionClose.width
                            text: root.state === "Choose" ? (root.status.clarification ? root.status.clarification.prompt : "Choose a window")
                                : root.status.intent && root.status.intent.type === "list_terminals" ? "Open terminals"
                                : root.status.intent && root.status.intent.type === "list_browsers" ? "Open browsers"
                                : root.status.intent && root.status.intent.type === "list_x" ? "Open X windows"
                                : "Open windows"
                            textFormat: Text.PlainText
                            color: Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.font.body
                            font.bold: true
                            wrapMode: Text.Wrap
                        }
                        Button {
                            id: selectionClose
                            text: "Close"
                            focusable: true
                            onClicked: root.action(root.state === "WindowList" ? "dismiss-window-list" : "cancel", root.state === "WindowList" ? undefined : "")
                        }
                    }
                Column {
                    visible: root.state === "WindowList"
                    width: parent.width
                    spacing: Style.space(8)
                    Text {
                        width: parent.width
                        text: (root.status.window_list || []).length ? "Choose a window to focus" : (root.status.message || "")
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                    }
                    Text {
                        text: (root.status.window_list || []).length
                            ? "Enter to close · Tab to choose a window · Esc to dismiss"
                            : "Enter or Esc to dismiss"
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body * 0.9
                    }
                    Repeater {
                        model: root.status.window_list || []
                        Rectangle {
                            required property var modelData
                            activeFocusOnTab: true
                            Keys.onReturnPressed: root.action("focus-listed-window", modelData.address)
                            Keys.onEnterPressed: root.action("focus-listed-window", modelData.address)
                            onActiveFocusChanged: if (activeFocus) {
                                var top = mapToItem(selectionContent, 0, 0).y
                                selectionScroll.contentY = Math.max(0, Math.min(top,
                                    selectionScroll.contentHeight - selectionScroll.height))
                            }
                            width: parent.width
                            height: windowDetails.implicitHeight + Style.space(24)
                            radius: Style.space(8)
                            color: activeFocus || listedWindowMouse.containsMouse
                                ? Qt.alpha(Color.accent, 0.22) : Qt.alpha(Color.foreground, 0.07)
                            border.width: 1
                            border.color: activeFocus || listedWindowMouse.containsMouse
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
                                    color: Color.foreground
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.body * 0.95
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    visible: !!modelData.names_note
                                    text: modelData.names_note || ""
                                    textFormat: Text.PlainText
                                    color: Color.foreground
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.body * 0.95
                                    wrapMode: Text.Wrap
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
                    visible: root.state === "Choose" && !!root.status.clarification
                    width: parent.width
                    spacing: Style.space(8)
                    Repeater {
                        id: selectionChoices
                        model: root.status.clarification ? root.status.clarification.choices : []
                        Button {
                            required property var modelData
                            focusable: true
                            width: parent.width
                            text: modelData.label
                            onClicked: root.action("choose-window", modelData.token)
                        }
                    }
                    Button { text: "Cancel"; focusable: true; bordered: true; onClicked: root.action("cancel", "") }
                }
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
                        text: root.state === "WindowList" ? (root.status.intent && root.status.intent.type === "list_terminals" ? "Open terminals" : root.status.intent && root.status.intent.type === "list_browsers" ? "Open browsers" : root.status.intent && root.status.intent.type === "list_x" ? "Open X windows" : "Open windows") : "Skipper · " + root.state
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
                Text {
                    width: parent.width
                    visible: root.state !== "WindowList"
                    text: root.status.transcript || (root.state === "TextEntry" ? "Written command" : "Super + R to choose a command.")
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
                        text: "← Back"
                        enabled: root.alive && !!root.status.layout_history && root.status.layout_history.can_back
                        onClicked: root.action("layout-back")
                    }
                    Button {
                        text: "Forward →"
                        enabled: root.alive && !!root.status.layout_history && root.status.layout_history.can_forward
                        onClicked: root.action("layout-forward")
                    }
                    Button {
                        text: "Save view"
                        enabled: root.alive && root.state !== "Working"
                        onClicked: root.action("layout-save")
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.status.layout_history ? root.status.layout_history.position + "/" + root.status.layout_history.count : ""
                        color: Color.muted
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body * 0.85
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
