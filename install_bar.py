"""Install Keety's user-owned Omarchy bar widget and login launcher."""
import json
import os
from pathlib import Path
import shutil
import time

root = Path(__file__).resolve().parent
config = Path.home()/'.config'
shell = config/'omarchy/shell.json'
backup = shell.with_name(f'shell.json.bak.keety-{time.time_ns()}')
shutil.copy2(shell,backup)
data = json.loads(shell.read_text())
plugin = config/'omarchy/plugins/greg.keety'
if plugin.exists():
    shutil.copytree(plugin, config/f'omarchy/backups/greg.keety-{time.time_ns()}')
shutil.copytree(root/'config/keety-bar',plugin,dirs_exist_ok=True)
layout = data.setdefault('bar',{}).setdefault('layout',{})
for section in ['left','center','right']:
    layout[section] = [entry for entry in layout.get(section,[]) if entry.get('id')!='greg.keety']
layout['right'].insert(0,{'id':'greg.keety','launcher':str(root/'launch.sh'),
    'explorerLauncher':str(root/'launch-explorer.sh'),
    'statusPath':str(Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'keety-{os.getuid()}-status.json')})
shell.write_text(json.dumps(data,indent=2)+'\n')
# Desktop Exec quoting uses its own escaping rules, not shell quoting.
launcher = str(root/'launch.sh').replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
autostart = config/'autostart/keety.desktop'
autostart.parent.mkdir(parents=True,exist_ok=True)
autostart.write_text('[Desktop Entry]\nType=Application\nName=Keety\nComment=Background voice commands\nExec="'+launcher+'"\nTerminal=false\n')
print(f'Installed Keety bar widget. Shell config backup: {backup}')
