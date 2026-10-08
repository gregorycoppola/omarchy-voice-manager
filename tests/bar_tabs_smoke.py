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
  Skipper.BarWidget { id: widget; property string captured: ""; property string capturedToken: ""; function action(name, token) { captured=name; capturedToken=token || "" } settings: ({statusPath:"/nonexistent/skipper-path-smoke.json"}) }
  Timer { interval: 300; running: true; onTriggered: {
   try {
    var input = null;
    function findInput(item) {
     if (item.objectName === "writtenWords") return item;
     for (var child of (item.children || [])) { var found=findInput(child); if(found) return found; }
     return null;
    }
    widget.readStatus({state:"TextEntry", updated:Date.now()/1000, session:"tabs", panel_epoch:1,
      written_entry:{token:"tabs",text:"",suggestions:[],dynamic_suggestions:[
        {command:"browser:focus-tab",text:"focus tab",forms:["focus tab","list browser tabs"],pickerWindow:true}],counts:{}}});
    for (var item of widget.data) { if (item.contentItem) input=findInput(item.contentItem); if(input)break; }
    if (!input) throw new Error("Input missing");
    input.text="focus tab";
    widget.expandTabPrefix();
    if(widget.captured !== "submit-written") throw new Error("Tab level did not automatically open");
    widget.readStatus({state:"WindowList",updated:Date.now()/1000,session:"tabs",panel_epoch:2,list_kind:"tabs",window_list:[
      {address:"one",title:"Wordmark",kind:"Browser tab",browser_tab:{url:"http://localhost:8766"}},
      {address:"two",title:"Mail",kind:"Browser tab",browser_tab:{url:"https://mail.example.com"}}]});
    var panel=null;
    for(var item of widget.data) if(item.objectName === "selectionPanel") panel=item;
    if(!panel) throw new Error("Tab panel missing");
    function findSearch(item) {
      if(item.objectName === "tabSearch") return item;
      for(var child of (item.children || [])) {var found=findSearch(child); if(found)return found;}
      return null;
    }
    var search=findSearch(panel.contentItem);
    if(!search) throw new Error("Search missing");
    search.text="wdmk";
    if(panel.tabRows.length !== 1 || panel.tabRows[0].address !== "one") throw new Error("Fuzzy filter failed");
    panel.chooseTab();
    if(widget.captured !== "focus-listed-window" || widget.capturedToken !== "one") throw new Error("Wrong tab selection");
    search.text="zzzz";
    widget.captured="";
    panel.chooseTab();
    if(panel.tabRows.length || widget.captured) throw new Error("No-results activated a tab");
    console.log("PASS tab QML: automatic level, fuzzy filter, selection, no-results")
   } catch (error) { console.error("FAIL " + error) }
   finally { widget.writtenOpen = false; Qt.quit() }
  }}
  Timer { interval: 3000; running: true; onTriggered: Qt.quit() }
 }
}''')
    result=subprocess.run(['quickshell','-p',str(folder)],capture_output=True,text=True,timeout=6)
    output=result.stdout+result.stderr
    print(output)
    if result.returncode or 'PASS tab QML' not in output or 'FAIL ' in output: raise SystemExit(1)
