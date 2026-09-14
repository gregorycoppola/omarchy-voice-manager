const {test} = require('node:test');
const assert = require('node:assert/strict');
const {bringUpSite} = require('../browser_tabs.js');
const site = {url:'https://github.com/', host:'github.com'};
function setup(windows) {
  const calls=[];
  const all=structuredClone(windows);
  global.chrome={
    windows:{
      getAll:async()=>all.filter(w=>w.type==='normal'),
      update:async(id,opts)=>{calls.push(['focus',id]);},
      create:async(opts)=>{calls.push(['window',opts.url]); const w={id:90,type:'normal',tabs:[{id:91,windowId:90,url:opts.url}]};all.push(w);return w;},
    },
    tabs:{
      create:async(opts)=>{calls.push(['tab',opts.windowId,opts.url]); const t={id:80,windowId:opts.windowId,url:opts.url};all.find(w=>w.id===opts.windowId).tabs.push(t);return t;},
      update:async(id,opts)=>{calls.push(['activate',id]);all.flatMap(w=>w.tabs).find(t=>t.id===id).active=opts.active;},
      get:async(id)=>all.flatMap(w=>w.tabs).find(t=>t.id===id),
    },
  };
  return calls;
}
const normal=(id,tabs,extra={})=>({id,type:'normal',tabs:tabs.map(t=>({...t,windowId:id})),...extra});
test('existing matching tab reused without navigation or creation',async()=>{
 const calls=setup([normal(1,[{id:3,url:'https://github.com/gregorycoppola/skipper'}])]);
 assert.deepEqual(await bringUpSite(site),{reused:true,tabId:3,windowId:1});
 assert.deepEqual(calls,[['activate',3],['focus',1]]);
});
test('missing site opens a tab in existing window, repeated command reuses it',async()=>{
 const calls=setup([normal(1,[{id:3,url:'chrome://newtab/'}])]);
 assert.equal((await bringUpSite(site)).reused,false);
 assert.equal((await bringUpSite(site)).reused,true);
 assert.equal(calls.filter(c=>c[0]==='tab').length,1);
 assert.equal(calls.filter(c=>c[0]==='window').length,0);
});
test('duplicate matches prefer focused window then most recently used tab',async()=>{
 setup([normal(1,[{id:1,url:site.url,lastAccessed:900}]),normal(2,[{id:2,url:site.url,lastAccessed:100},{id:3,url:site.url,lastAccessed:200}],{focused:true})]);
 assert.equal((await bringUpSite(site)).tabId,3);
});
test('new tab uses most recent regular window, excludes private and control windows',async()=>{
 const calls=setup([normal(1,[{id:1,url:'https://example.com',lastAccessed:10}]),normal(2,[{id:2,url:'https://example.org',lastAccessed:20}]),normal(3,[{id:3,url:'chrome-extension://control/status.html'}],{focused:true}),normal(4,[{id:4,url:site.url}],{incognito:true})]);
 assert.equal((await bringUpSite(site)).windowId,2);
 assert.equal(calls[0][0],'tab');
});
test('no browser window creates normal window; app windows are excluded',async()=>{
 const calls=setup([{id:1,type:'app',tabs:[{id:3,url:site.url}]}]);
 assert.equal((await bringUpSite(site)).windowId,90);
 assert.deepEqual(calls[0],['window',site.url]);
});
test('host matching rejects lookalike domains and other protocols',async()=>{
 setup([normal(1,[{id:1,url:'https://github.com.evil.test/'},{id:2,url:'https://evil.test/github.com'},{id:3,url:'http://github.com/'}])]);
 assert.equal((await bringUpSite(site)).reused,false);
});
test('pending site navigation is reused to prevent duplicate tabs',async()=>{
 setup([normal(1,[{id:1,url:'about:blank',pendingUrl:site.url}])]);
 assert.equal((await bringUpSite(site)).reused,true);
});
