const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const c = vm.createContext({});
vm.runInContext(fs.readFileSync('config/skipper-bar/CommandSearch.js', 'utf8'), c);
const tabs = [
 {address:'a',title:'Wordmark',browser_tab:{url:'http://localhost:8000'}},
 {address:'b',title:'Wordmark',browser_tab:{url:'http://localhost:8000'}},
 {address:'c',title:'Documentation',browser_tab:{url:'https://example.org/help'}}
];
const ids = q => Array.from(c.rankTabs(q,tabs), row => row.address);
assert.deepEqual(ids(''), ['a','b','c']);
assert.deepEqual(ids('wdmk'), ['a','b']);
assert.deepEqual(ids('EXMPL'), ['c']);
assert.deepEqual(ids('zzzz'), []);
console.log('Tab fuzzy search preserves duplicates, searches URLs, and excludes nonmatches');
