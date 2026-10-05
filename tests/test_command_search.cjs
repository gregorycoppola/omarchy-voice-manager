const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('config/skipper-bar/CommandSearch.js', 'utf8'), context);
const search = (query, suggestions = [], dynamic = [], counts = {}) =>
  Array.from(context.search(query, suggestions, dynamic, counts));
const score = (text, query) => context.textMatchScore(text, query);
const suggestions = [
  {command: 'browser', text: 'open the browser', forms: ['open the browser', 'open chrome']},
  {command: 'window', text: 'open window', forms: ['open window']},
  {command: 'terminals', text: 'open terminals', forms: ['open terminals']}
];

// Ordered-character filtering allows gaps, but preserves character order.
assert.equal(search('opn', suggestions)[0], 'open chrome');
assert.equal(search('o p e n w i n', suggestions)[0], 'open window');
assert.deepEqual(search('open chrmoe', suggestions), []);
assert.equal(search('open chrome', suggestions)[0], 'open chrome');
assert.deepEqual(search('zzzz', suggestions), []);
assert.equal(score('Open Chrome', 'openchrome'), 1);
assert.ok(score('open chrome', 'open chrmoe') > score('open window', 'open chrmoe'));

// No prefix tier: an equally costly alignment at the end has the same score.
assert.equal(score('open zz', 'open'), score('zz open', 'open'));
assert.ok(score('zopen', 'open') > score('open many extra letters', 'open'));
assert.ok(score('abc', 'abc') > score('axbcd', 'abc'));
assert.equal(score('abc', ''), 0);
assert.equal(score('', 'abc'), 0);

// Frequency cannot change ordering, even for exact lexical ties or empty input.
const ties = [
  {command: 'first', text: 'open aa'},
  {command: 'second', text: 'open bb'}
];
assert.deepEqual(search('open', ties, [], {second: 1000000}), ['open aa', 'open bb']);
for (const query of ['', 'opn', 'open', 'open chrmoe']) {
  assert.deepEqual(search(query, suggestions, [], {terminals: 1000000, window: 99}),
    search(query, suggestions));
}
assert.deepEqual(search('', suggestions), suggestions.map(row => row.text));
const ranked = context.rank('open', ties, [], {second: 99});
assert.equal(ranked[0].textScore, ranked[1].textScore);
assert.equal(ranked[0].frequencyScore, 0);
assert.equal(ranked[1].frequencyScore, 99);
assert.equal(context.frequencyScore('bad', {bad: -2}), 0);

// Supported dynamic forms participate, and aliases can supply the displayed text.
const dynamic = [{command: 'desktop-app:tasks', text: 'open task board', forms: ['launch task board']}];
assert.equal(search('launch task', suggestions, dynamic)[0], 'launch task board');
assert.equal(search('focus', [],
  [{command: 'focus-window:one', text: 'focus the firefox window', forms: ['focus firefox']}])[0],
  'focus firefox');
assert.equal(search('minimize',
  [{command: 'window:hide', text: 'hide this window', forms: ['minimize this window']}])[0],
  'minimize this window');

// Duplicate displayed rows collapse; unusual names remain valid keys.
assert.equal(search('open', ties.concat(ties)).length, 2);
assert.equal(search('', [{command: 'special', text: '__proto__'}])[0], '__proto__');
const many = Array.from({length: 30}, (_, i) => ({command: 'command:' + i, text: 'command ' + i}));
assert.equal(search('', many).length, 10);
assert.equal(search('command 29', many)[0], 'command 29');
assert.equal(context.rank('', many).length, 30);
console.log('Text-only fuzzy command ranking: passed');

// Reject before expensive scoring and bound work even with many alternatives.
const originalScore = context.textMatchScore;
let calls = 0;
context.textMatchScore = (...args) => { calls++; return originalScore(...args); };
const large = Array.from({length: 200}, (_, i) => ({command: 'item:' + i,
  text: 'open item ' + i, forms: ['open application item ' + i, 'launch item ' + i]}));
search('zzzz', large);
assert.equal(calls, 0);
search('', large);
assert.equal(calls, 0);
search('open', large);
assert.ok(calls <= 50);
assert.equal(search('open item 199', large)[0], 'open item 199');
assert.equal(search('a', [{command: 'long', text: 'a very long option name'}])[0], 'a very long option name');
context.textMatchScore = originalScore;
console.log('Subsequence filter and bounded reranking: passed');

const listing = [{command:'windows:list', text:'list all windows'}];
assert.deepEqual(search('list windows', listing), ['list all windows']);
assert.deepEqual(search('lst wnd', listing), ['list all windows']);
assert.deepEqual(search('windows list', listing), []);
assert.deepEqual(search('listt windows', listing), []);
assert.deepEqual(search('LIST   WINDOWS', listing), ['list all windows']);
assert.equal(context.containsSubsequence('abc', ''), true);
assert.equal(context.containsSubsequence('', 'a'), false);
assert.equal(context.containsSubsequence('abc', 'aa'), false);
