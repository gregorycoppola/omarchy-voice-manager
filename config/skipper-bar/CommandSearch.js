// Pure subsequence matching: prefix/substring first, then ordered characters.
// History arrives newest-first; ties preserve recency. No command is executed here.
function score(text, query) {
    text = text.toLowerCase(); query = query.toLowerCase().trim();
    if (!query) return 0;
    if (text === query) return 10000;
    if (text.indexOf(query) === 0) return 9000 - text.length;
    var at = text.indexOf(query);
    if (at >= 0) return 8000 - at - text.length;
    query = query.replace(/\s+/g, "");
    var position = -1, first = -1, bonus = 0;
    for (var i = 0; i < query.length; i++) {
        var next = text.indexOf(query[i], position + 1);
        if (next < 0) return -1;
        if (first < 0) first = next;
        if (next === position + 1) bonus += 5;
        if (next === 0 || text[next - 1] === " ") bonus += 10;
        position = next;
    }
    return 1000 + bonus - (position - first) - first;
}
function search(history, query) {
    return history.map(function(text, index) {
        return {text: text, index: index, score: score(text, query)};
    }).filter(function(row) { return row.score >= 0; })
      .sort(function(a, b) { return b.score - a.score || a.index - b.index; })
      .slice(0, 10).map(function(row) { return row.text; });
}
