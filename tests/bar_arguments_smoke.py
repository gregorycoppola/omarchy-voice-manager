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
    var input = null;
    function findInput(item) {
     if (item.objectName === "writtenWords") return item;
     for (var child of (item.children || [])) { var found=findInput(child); if(found) return found; }
     return null;
    }
    widget.readStatus({state:"TextEntry", updated:Date.now()/1000, session:"providers", panel_epoch:1,
      written_entry:{token:"providers",text:"",suggestions:[],dynamic_suggestions:[],counts:{},
       files:{query:"",loading:false,rows:[
        {id:"new",label:"z-new.txt",detail:"~/Documents",text:"Open file /home/user/Documents/z-new.txt"},
        {id:"old",label:"a-old.txt",detail:"~/Documents",text:"Open file /home/user/Documents/a-old.txt"}]},
       audio:{output:{rows:[{id:"speaker",label:"Speakers",detail:"Built-in",current:true,text:"Switch audio output to Speakers"}]}},
       controls:{rows:[{id:"enable:wifi",verb:"enable",label:"Wi-Fi",text:"enable Wi-Fi",detail:"Off",available:true}]}}});
    widget.writtenOpen = false;
    for (var item of widget.data) { if (item.contentItem) input=findInput(item.contentItem); if(input)break; }
    if (!input) throw new Error("Input missing");
    widget.resetArguments(); input.text="";
    widget.argumentPath=["prefix:open","files"];
    if(widget.pickerRows.length !== 2 || widget.pickerRows[0].fileChoice !== "new") throw new Error("Recent order lost");
    widget.historySelection=0; widget.advanceArgument();
    if(widget.acceptedFile !== "new" || !widget.commandComplete) throw new Error("File selection lost identity");
    widget.resetArguments(); input.text="";
    widget.argumentPath=["prefix:switch","audio:output"];
    if(widget.pickerRows[0].audioChoice.id !== "speaker") throw new Error("Audio provider missing");
    widget.historySelection=0; widget.advanceArgument();
    if(widget.acceptedAudio.id !== "speaker" || widget.canQueueCommand) throw new Error("Audio selection invalid");
    widget.resetArguments(); input.text="";
    widget.argumentPath=["control:enable"];
    if(widget.pickerRows[0].controlChoice !== "enable:wifi") throw new Error("Control provider missing");
    widget.historySelection=0; widget.advanceArgument();
    if(widget.acceptedControl !== "enable:wifi" || widget.canQueueCommand) throw new Error("Control selection invalid");
    widget.readStatus({state:"TextEntry", updated:Date.now()/1000, session:"optional", panel_epoch:2,
      written_entry:{token:"optional",text:"open Chromium",suggestions:[],dynamic_suggestions:[
        {command:"desktop-app:chromium",text:"open Chromium",forms:["open chromium"],optionalOpen:true}], counts:{}}});
    widget.writtenOpen=false;
    if(widget.selectedCommand() !== "open Chromium in this workspace") throw new Error("Default opening unavailable");
    if(!widget.canQueueCommand) throw new Error("Optional command cannot queue");
    widget.advanceArgument();
    if(widget.pickerRows[0].text !== "in this workspace") throw new Error("Current workspace must be first");
    widget.historySelection=2; widget.advanceArgument();
    if(widget.selectedCommand() !== "open Chromium in workspace 2") throw new Error("Workspace default cannot run");
    widget.historySelection=1; widget.advanceArgument();
    if(!widget.commandComplete || widget.selectedCommand() !== "open Chromium in workspace 2 and tile") throw new Error("Tiling argument lost");
    widget.previousArgument();
    if(widget.commandComplete || widget.pickerRows.length !== 2) throw new Error("Optional argument back failed");
    widget.readStatus({state:"TextEntry", updated:Date.now()/1000, session:"tile-pair", panel_epoch:3,
      written_entry:{token:"tile-pair",text:"tile", suggestions:[
       {command:"apps:tile",text:"tile all apps"}, {command:"browsers:tile",text:"tile all browsers"},
       {command:"terminals:tile",text:"tile all terminals"}, {command:"windows:tile",text:"tile the windows"},
       {command:"browsers:list",text:"list browsers"},{command:"terminals:list",text:"list terminals"},
       {command:"windows:list",text:"list windows"}], dynamic_suggestions:[
       {command:"picker:tile-pair",text:"tile two specific windows",forms:["tile two specific windows"],
        tileWindows:[{id:"one",label:"editor"},{id:"two",label:"chromium"},{id:"three",label:"notes"}]}],counts:{}}});
    widget.writtenOpen=false;
    if(widget.historyMatches.slice(0,3).join(",") !== "all windows,all terminals,all browsers") throw new Error("Tile category order lost in ranking");
    widget.historySelection=3; widget.advanceArgument();
    if(widget.argumentPrompt !== "CHOOSE THE FIRST WINDOW" || widget.pickerRows.length !== 3) throw new Error("First tile choice missing");
    widget.historySelection=0; widget.advanceArgument();
    if(widget.argumentPrompt !== "CHOOSE THE SECOND WINDOW" || widget.pickerRows.length !== 2) throw new Error("Second tile choice missing");
    if(widget.pickerRows.some(row => row.text === "editor")) throw new Error("First window repeated");
    widget.historySelection=0; widget.advanceArgument();
    if(widget.selectedCommand() !== "tile editor and chromium" || !widget.commandComplete) throw new Error("Pair command incorrect");
    widget.previousArgument();
    if(widget.commandComplete || widget.pickerRows.length !== 2) throw new Error("Pair back failed");
    widget.resetArguments(); input.text="list";
    if(widget.historyMatches.slice(0,3).join(",") !== "all windows,all terminals,all browsers") throw new Error("List category order lost in ranking");
    widget.resetArguments(); input.text="tile all term";
    if(widget.argumentPrompt !== "CHOOSE A WORKSPACE" || widget.prefixPreview.query !== "") throw new Error("Unique abbreviated category did not advance");
    if(widget.selectedCommand() !== "tile all terminals in this workspace") throw new Error("Abbreviated category lost default");
    input.text="tile all terminals";
    if(widget.selectedCommand() !== "tile all terminals in this workspace") throw new Error("Default workspace not selected");
    if(widget.argumentPrompt !== "CHOOSE A WORKSPACE") throw new Error("Workspace level not shown");
    input.text="tile all terminals in workspace 2";
    if(widget.selectedCommand() !== "tile all terminals in workspace 2") throw new Error("Numbered workspace not selected");
    input.text="tile all terminals in workspace 0";
    if(widget.pickerRows.length) throw new Error("Invalid workspace fell back to default");
    input.text="tile all terminals";
    if(widget.selectedCommand() !== "tile all terminals in this workspace") throw new Error("Default did not restore");
    console.log("PASS provider QML: recent order, file/audio/control identities, and queue restrictions")
   } catch (error) { console.error("FAIL " + error) }
   finally { widget.writtenOpen = false; Qt.quit() }
  }}
  Timer { interval: 3000; running: true; onTriggered: Qt.quit() }
 }
}''')
    result=subprocess.run(['quickshell','-p',str(folder)],capture_output=True,text=True,timeout=6)
    output=result.stdout+result.stderr
    print(output)
    if result.returncode or 'PASS provider QML' not in output or 'FAIL ' in output: raise SystemExit(1)
