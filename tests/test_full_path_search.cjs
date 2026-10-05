const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const levels = vm.createContext({});
const search = vm.createContext({});
vm.runInContext(fs.readFileSync('config/skipper-bar/CommandLevels.js', 'utf8'), levels);
vm.runInContext(fs.readFileSync('config/skipper-bar/CommandSearch.js', 'utf8'), search);
const tree = levels.build([
    {command: 'browser', text: 'open the browser', forms: ['launch the browser']},
    {command: 'terminal', text: 'open a new terminal'},
    {command: 'list-browser', text: 'list open browser windows'},
    {command: 'tile-browser', text: 'tile this window and open browser'},
    {command: 'window:move-workspace:3', text: 'move this window to workspace 3'},
    {command: 'move:other_screen', text: 'move to other screen'}
], []);
function results(query, path = []) {
    const preview = levels.preview(tree, path, query, false);
    assert.equal(preview.query, query, 'Preview must preserve input exactly');
    const ranked = search.rank(query, preview.rows, [], {});
    return {preview, ranked};
}
for (const query of ['ope', 'openb', 'openbrow', 'open brow', 'opbr', 'OPENBROW']) {
    const {preview, ranked} = results(query);
    assert.ok(preview.rows.some(row => row.value === 'open the browser'), query);
    assert.equal(preview.frames.every(frame => frame.text === query), true);
    if (query !== 'ope') assert.equal(ranked[0].command, 'browser', query);
}
assert.equal(results('openbrow', ['prefix:open']).ranked[0].command, 'browser');
assert.ok(results('ope').preview.rows.some(row => row.value === 'open a new terminal'));
assert.ok(results('').preview.rows.some(row => row.id === 'prefix:move'));
assert.equal(results('zzzzzz').preview.rows.length, 0);
assert.equal(results('moveworkspace3').ranked[0].command, 'window:move-workspace:3');
assert.equal(results('launchbrow').ranked[0].command, 'browser');
const windows = levels.build([], [{command: 'move-window:test', text: 'move this window', pickerWindow: true,
    destinations: [{text: 'Workspace 2', suffix: 'workspace 2'}, {text: 'Laptop monitor', suffix: 'monitor eDP-1'}]}]);
const moved = levels.preview(windows, [], 'movethisworkspace2', false);
assert.equal(moved.rows[0].value, 'move this window to workspace 2');
assert.equal(moved.query, 'movethisworkspace2');
console.log('Full-path search: compact input, aliases, backspacing, nested destinations, and window providers passed');
const stickyTree = levels.build([
 {command:'discord',text:'open discord'},
 {command:'browser',text:'open the browser'},
 {command:'list',text:'list open discord windows'},
 {command:'close',text:'close discord'}
], []);
for (const finalQuery of ['opediscord', 'opendiscord']) {
 let memory = [], result;
 for(let i=1;i<=finalQuery.length;i++) {
  const query=finalQuery.slice(0,i);
  result=levels.rememberedPreview(stickyTree,[],query,false,memory);
  memory=result.checkpoints;
  assert.equal(result.query,query);
  if(i>=3) assert.equal(result.path[0],'prefix:open',query);
 }
 assert.equal(result.rows[0].value,'open discord');
 const checkpoint=memory[0];
 result=levels.rememberedPreview(stickyTree,[],checkpoint.text,false,memory);
 assert.equal(result.path[0],'prefix:open');
 result=levels.rememberedPreview(stickyTree,[],checkpoint.text.slice(0,-1),false,memory);
 assert.equal(result.path.length,0,'Backspace past checkpoint releases Open');
 result=levels.rememberedPreview(stickyTree,[],checkpoint.text.slice(0,-1),false,result.checkpoints);
 assert.equal(result.path.length,0,'Reactive reevaluation must not reenter released branch');
 result=levels.rememberedPreview(stickyTree,[],'close discord',false,memory);
 assert.equal(result.path[0],'prefix:close','Incompatible edit releases Open');
}
console.log('Remembered branch: incremental abbreviation, full spelling, checkpoint backspace, and incompatible edits passed');
const tileTree = levels.build([
 {command:'apps:tile', text:'tile all apps', forms:['tile all apps','tile the apps']},
 {command:'browsers:tile', text:'tile all browsers'},
 {command:'terminals:tile', text:'tile all the terminals'}
],[]);
const tileRows = levels.preview(tileTree, [], 'tile', false).rows;
assert.ok(tileRows.some(row => row.text === 'all apps' && row.value === 'tile all apps'));
assert.ok(tileRows.some(row => row.text === 'all browsers'));
assert.ok(tileRows.every(row => row.description.startsWith('This workspace')));
assert.equal(levels.preview(tileTree, [], 'tileopenapps', false).rows[0].value,'tile all apps');
console.log('Tile labels: open categories, current-workspace descriptions, and executable wording passed');
const monitorTree = levels.build([
 {command:'apps:tile',text:'tile all apps'},
 {command:'apps:tile-monitor:1',text:'tile the apps on monitor 1'},
 {command:'apps:tile-monitor:2',text:'tile the apps on monitor 2'},
 {command:'browsers:tile-monitor:2',text:'tile the browsers on monitor 2'}
],[]);
const monitorRoot = levels.preview(monitorTree,[],'tile',false).rows;
assert.equal(monitorRoot.length,2);
assert.ok(monitorRoot.some(row=>row.id==='tile-monitor'));
assert.ok(!monitorRoot.some(row=>/monitor [0-9]/i.test(row.text)));
const monitorMatch = levels.preview(monitorTree,[],'tileopenappsonmonitor2',false);
assert.equal(monitorMatch.rows[0].value,'tile the apps on monitor 2');
console.log('Tile monitor choices: grouped at the root, full path remains searchable');
