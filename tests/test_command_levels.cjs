const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const c = vm.createContext({});
vm.runInContext(fs.readFileSync('config/skipper-bar/CommandLevels.js', 'utf8'), c);
const items = [{command:'workspace:switch:3', text:'switch to workspace 3'}];
const windows = [{command:'picker:move:current', text:'move this window', forms:['move this window'],
 pickerWindow:true, destinations:[{text:'Workspace 3',suffix:'workspace 3'}, {text:'Laptop monitor',suffix:'monitor eDP-1'}]},
 {command:'picker:close:current', text:'close this window', forms:['close this window'],pickerWindow:true}];
const tree = c.build(items, windows, {output:{rows:[{id:'speaker',label:'Speakers',detail:'Built-in',current:true,text:'Switch audio output to Speakers'}]}},
 {rows:[{id:'document',label:'notes.md',detail:'~/Documents',text:'Open file /home/user/Documents/notes.md'}]},
 {rows:[{id:'enable:wifi',verb:'enable',label:'Wi-Fi',text:'enable Wi-Fi',detail:'Off',available:true}]});
const verbs = tree.map(row=>row.text);
for (const verb of ['open…','move…','close…','switch…','enable…','disable…','connect…','disconnect…']) assert.ok(verbs.includes(verb));
const path=['prefix:move','picker:move:current'];
assert.equal(c.level(tree,path).children.length,2);
assert.equal(c.level(tree,path).children[0].value,'move this window to workspace 3');
assert.equal(c.level(tree,path).children[1].value,'move this window to monitor eDP-1');
assert.equal(c.options(tree,path,'42')[0].value,'move this window to workspace 42');
for (const invalid of ['0','-1','1.5','1000000000','3; ls']) assert.equal(c.options(tree,path,invalid).length,2);
assert.equal(c.level(tree,['gone']).children.length,0);
const audio=c.level(tree,['prefix:switch','audio:output']);
assert.equal(audio.audioDirection,'output');
assert.equal(audio.children[0].audioChoice.id,'speaker');
assert.match(audio.children[0].description,/Current default/);
const files=c.level(tree,['prefix:open','files']);
assert.equal(files.fileProvider,true);
assert.equal(files.children[0].fileChoice,'document');
const control=c.level(tree,['control:enable']);
assert.equal(control.controlProvider,true);
assert.equal(control.children[0].controlChoice,'enable:wifi');
console.log('Verb, window, destination, file, audio and control hierarchy: passed');
const appsTree = c.build([], [{command:'desktop-app:chromium', text:'open Chromium', forms:['open chromium'],optionalOpen:true}]);
const appPreview=c.preview(appsTree,[],'open chromium',false);
assert.equal(appPreview.rows.length,1);
assert.equal(appPreview.rows[0].optionalArguments,true);
assert.equal(appPreview.rows[0].value,'open Chromium in this workspace');
assert.equal(appPreview.path.join('/'),'prefix:open');
const workspacePath=['prefix:open','desktop-app:chromium'];
const destinations=c.level(appsTree,workspacePath).children;
assert.equal(destinations[0].text,'in this workspace');
assert.equal(destinations[2].value,'open Chromium in workspace 2');
assert.equal(destinations[2].optionalArguments,true);
const layouts=c.level(appsTree,workspacePath.concat([destinations[2].id])).children;
assert.equal(layouts[1].value,'open Chromium in workspace 2 and tile');
const tiled=c.preview(appsTree,[],'open chromium in workspace 2 and tile',false);
assert.equal(tiled.rows.length,1);
assert.equal(tiled.rows[0].value,'open Chromium in workspace 2 and tile');
console.log('Optional opening: defaults, workspace arguments and chained tiling passed');
const categoryTree = c.build([
 {command:'apps:tile',text:'tile all apps'},
 {command:'browsers:tile',text:'tile all browsers'},
 {command:'terminals:tile',text:'tile all terminals'},
 {command:'windows:tile',text:'tile the windows'},
 {command:'browsers:list',text:'list browsers'},
 {command:'terminals:list',text:'list terminals'},
 {command:'windows:list',text:'list windows'}
], [{command:'picker:tile-pair',text:'tile two specific windows',forms:['tile two specific windows','tile two windows'],
 tileWindows:[{id:'one',label:'project terminal'},{id:'two',label:'chromium'},{id:'three',label:'notes'}]}]);
assert.equal(c.preview(categoryTree,[],'tile',false).rows.slice(0,4).map(row=>row.text).join(','),
 'all windows,all terminals,all browsers,all apps');
assert.equal(c.preview(categoryTree,[],'list',false).rows.map(row=>row.text).join(','),
 'all windows,all terminals,all browsers');
const pairPreview=c.preview(categoryTree,[],'tile two specific windows',false);
assert.equal(pairPreview.rows[0].id,'picker:tile-pair');
const firstPath=['prefix:tile','picker:tile-pair'];
assert.equal(c.level(categoryTree,firstPath).argumentPrompt,'CHOOSE THE FIRST WINDOW');
const first=c.level(categoryTree,firstPath).children[0];
const second=c.level(categoryTree,firstPath.concat(first.id));
assert.equal(second.argumentPrompt,'CHOOSE THE SECOND WINDOW');
assert.equal(second.children.length,2);
assert.equal(second.children[0].value,'tile project terminal and chromium');
assert.ok(!second.children.some(row=>row.text==='project terminal'));
assert.equal(c.preview(categoryTree,[],'tile project terminal and chromium',false).rows[0].value,
 'tile project terminal and chromium');
console.log('Tile/List category order and two named window levels passed');
