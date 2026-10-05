from pathlib import Path
import tempfile, subprocess
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='skipper-path-smoke-') as folder:
    folder=Path(folder)
    for source in Path('/usr/share/omarchy/shell').iterdir():
        if source.is_dir(): (folder/source.name).symlink_to(source)
    (folder/'skipper').symlink_to(root/'config/skipper-bar')
    (folder/'shell.qml').write_text('''import QtQuick
import Quickshell
import "skipper" as Skipper
ShellRoot {
 PanelWindow {
  visible: false
  Skipper.BarWidget { id: widget; settings: ({statusPath:"/nonexistent/skipper-path-smoke.json"}) }
  Timer { interval: 300; running: true; onTriggered: {
   try {
    for (var query of ["ope", "openbrow", "open brow", "opbr", "ope", ""]) {
     widget.readStatus({state:"TextEntry", updated:Date.now()/1000, session:"smoke", panel_epoch:1,
      written_entry:{token:query + Math.random(), text:query, suggestions:[
       {command:"browser",text:"open the browser",forms:[]},
       {command:"terminal",text:"open a new terminal",forms:[]}
      ],dynamic_suggestions:[],counts:{}}})
     widget.writtenOpen = false
     if (widget.snapshot().writtenText !== query) throw new Error("Input changed: " + query)
     if (query === "openbrow" || query === "opbr") {
      if (widget.selectedCommand() !== "open the browser") throw new Error("Wrong selection")
      widget.previousArgument()
      if (widget.snapshot().writtenText !== query) throw new Error("Back lost query")
     }
    }
    widget.advanceArgument()
    if (widget.snapshot().writtenText !== "") throw new Error("Branch selection replaced input")
    function findInput(item) {
     if (item.objectName === "writtenWords") return item;
     for (var child of (item.children || [])) { var found = findInput(child); if (found) return found; }
     return null;
    }
    // The input belongs to a PanelWindow rather than the bar visual tree.
    var input = null;
    for (var item of widget.data) { if (item.contentItem) input = findInput(item.contentItem); if (input) break; }
    if (!input) throw new Error("Input missing");
    widget.resetArguments();
    for (var query of ["o", "op", "ope", "open", "openb", "openbrow"]) {
     input.text = query;
     input.textEdited();
     if (query.length >= 3 && widget.prefixPreview.path[0] !== "prefix:open") throw new Error("Open branch lost");
     if (input.text !== query) throw new Error("Typing changed input");
    }
    if (widget.selectedCommand() !== "open the browser") throw new Error("Live incremental selection failed");
    var checkpoint = widget.matchCheckpoints[0].text;
    input.text = checkpoint.slice(0, -1); input.textEdited();
    if (widget.prefixPreview.path.length) throw new Error("Checkpoint did not release");
    console.log("PASS full-path QML input, selection, back, explicit branch selection, and remembered typing")
   } catch (error) { console.error("FAIL " + error) }
   finally { widget.writtenOpen = false; Qt.quit() }
  }}
  Timer { interval: 3000; running: true; onTriggered: Qt.quit() }
 }
}''')
    result=subprocess.run(['quickshell','-p',str(folder)],capture_output=True,text=True,timeout=6)
    output=result.stdout+result.stderr
    print(output)
    if result.returncode or 'PASS full-path' not in output or 'FAIL ' in output: raise SystemExit(1)
