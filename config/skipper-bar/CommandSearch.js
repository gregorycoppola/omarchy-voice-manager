// Independent signals. Ranking currently uses text only; frequency is diagnostic.
var SKIP_COST = 0.25;
var TYPO_COST = 1;
var TRANSPOSE_COST = 0.75;
var RERANK_LIMIT = 50;

function normalize(text) {
    return text.toLowerCase().replace(/\s+/g, "");
}

// Linear ordered-character filter: the query may skip candidate characters,
// but cannot reorder them or reuse one character for repeated query letters.
function containsSubsequence(target, query) {
    var next = 0;
    for (var i = 0; i < target.length && next < query.length; i++) {
        if (target[i] === query[next]) next++;
    }
    return next === query.length;
}

// Weighted edit alignment (restricted adjacent transpositions). Skipping letters
// in the option is cheap so incomplete input and abbreviations remain useful.
// Rolling rows keep memory linear in the option length.
function textMatchScore(text, query) {
    var target = normalize(text);
    query = normalize(query);
    if (!query) return 0;
    if (!target) return 0;
    var previous = [];
    var beforePrevious = null;
    for (var j = 0; j <= target.length; j++) previous[j] = j * SKIP_COST;
    for (var i = 1; i <= query.length; i++) {
        var current = [i * TYPO_COST];
        for (var j = 1; j <= target.length; j++) {
            current[j] = Math.min(
                previous[j] + TYPO_COST,
                current[j - 1] + SKIP_COST,
                previous[j - 1] + (query[i - 1] === target[j - 1] ? 0 : TYPO_COST));
            if (i > 1 && j > 1 && query[i - 1] === target[j - 2]
                    && query[i - 2] === target[j - 1]) {
                current[j] = Math.min(current[j], beforePrevious[j - 2] + TRANSPOSE_COST);
            }
        }
        beforePrevious = previous;
        previous = current;
    }
    // Normalize against deleting the whole query and skipping the whole option.
    return Math.max(0, 1 - previous[target.length]
        / (query.length * TYPO_COST + target.length * SKIP_COST));
}

function frequencyScore(command, counts) {
    var count = Number((counts || {})[command]);
    return isFinite(count) && count > 0 ? count : 0;
}

// Scan all phrases cheaply, then score at most 50 options. For the current
// edit costs the shortest subsequence-matching form is the best form per option.
function rank(query, suggestions, dynamicSuggestions, counts) {
    var normalizedQuery = normalize(query);
    var rows = [];
    (suggestions || []).concat(dynamicSuggestions || []).forEach(function(item, index) {
        var display = item.text;
        var length = Infinity;
        if (normalizedQuery) {
            [item.text].concat(item.forms || []).forEach(function(form) {
                var normalized = normalize(form);
                if (containsSubsequence(normalized, normalizedQuery) && normalized.length < length) {
                    display = form;
                    length = normalized.length;
                }
            });
            if (length === Infinity) return;
        }
        rows.push({command: item.command, text: display, index: index,
            matchLength: length, textScore: 0,
            frequencyScore: frequencyScore(item.command, counts)});
    });
    if (normalizedQuery) {
        rows.sort(function(a, b) { return a.matchLength - b.matchLength || a.index - b.index; });
    }
    // Deduplicate before the budget so duplicates cannot crowd out other options.
    var seen = Object.create(null);
    rows = rows.filter(function(row) {
        var key = row.text.toLowerCase();
        if (seen[key]) return false;
        seen[key] = true;
        return true;
    }).slice(0, RERANK_LIMIT);
    if (normalizedQuery) rows.forEach(function(row) {
        row.textScore = textMatchScore(row.text, normalizedQuery);
    });
    rows.sort(function(a, b) {
        // Stable catalog order breaks exact lexical ties. History has no effect.
        return b.textScore - a.textScore || a.index - b.index;
    });
    return rows;
}

function search(query, suggestions, dynamicSuggestions, counts) {
    return rank(query, suggestions, dynamicSuggestions, counts).slice(0, 10)
        .map(function(row) { return row.text; });
}
