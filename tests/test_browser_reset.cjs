const {test} = require('node:test');
const assert = require('node:assert/strict');
const {inspectResetWindow, resetWindowTabs} = require('../browser_reset.js');

function setup({focused=true, incognito=false, controlInTarget=false, extraAfterClose=false}={}) {
  const calls=[];
  const target={id:1, focused, incognito, tabs:[{id:10,windowId:1},{id:11,windowId:1}]};
  const other={id:2, focused:false, tabs:[{id:20,windowId:2}]};
  const control={id:99,windowId:controlInTarget?1:2};
  (controlInTarget?target:other).tabs.push(control);
  global.chrome={windows:{getAll:async()=>[target,other]},tabs:{
    getCurrent:async()=>control,
    create:async(opts)=>{calls.push(['create',opts]);const blank={id:30,windowId:opts.windowId};target.tabs.push(blank);return blank;},
    remove:async(ids)=>{calls.push(['remove',ids]);target.tabs=target.tabs.filter(t=>!ids.includes(t.id));},
    query:async()=>extraAfterClose?[...target.tabs,{id:40}]:target.tabs,
  }};
  return {calls,target,other};
}

test('create blank before closing selected tabs, preserve other window',async()=>{
  const {calls,target,other}=setup();
  assert.deepEqual(await inspectResetWindow(),{windowId:1});
  const original=structuredClone(other);
  assert.deepEqual(await resetWindowTabs(1),{windowId:1,tabId:30,closed:2,closeControl:false});
  assert.equal(calls[0][0],'create');
  assert.equal(calls[0][1].url,'about:blank');
  assert.deepEqual(calls[1],['remove',[10,11]]);
  assert.deepEqual(target.tabs,[{id:30,windowId:1}]);
  assert.deepEqual(other,original);
});
test('control tab closure is deferred until extension evaluation returns',async()=>{
  const {calls}=setup({controlInTarget:true});
  assert.equal((await resetWindowTabs(1)).closeControl,true);
  assert.deepEqual(calls[1],['remove',[10,11]]);
});
test('wrong window, private window, and lost focus make no mutations',async()=>{
  for(const options of [{focused:false},{incognito:true},{}]) {
    const {calls}=setup(options);
    await assert.rejects(resetWindowTabs(Object.keys(options).length?1:999));
    assert.deepEqual(calls,[]);
  }
});
test('new or unclosed tabs cannot be reported as successfully cleared',async()=>{
  setup({extraAfterClose:true});
  await assert.rejects(resetWindowTabs(1),/Some tabs remain/);
});
