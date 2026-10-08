// Picker-only hierarchy. Leaves retain supported executable wording.
function leaf(item, text, forms) {
    return {id: item.command, command: item.command, text: text || item.text,
        forms: forms || item.forms || [], value: item.text, matchWording: text === undefined};
}
function branch(id, text, forms, children, prefix) {
    return {id: id, command: id, text: text, forms: forms, children: children, prefix: prefix};
}
// Executable branches: Enter runs the current defaults; Tab adds an argument.
function openOptions(item) {
    var base = item.text;
    var destinations = ['this workspace'];
    for (var n = 1; n <= 10; n++) destinations.push('workspace ' + n);
    var node = branch(item.command, base, item.forms || [base], function() {
        return destinations.map(function(destination) {
            var value = base + ' in ' + destination;
            var choice = branch(item.command + ':' + destination, 'in ' + destination,
                ['in ' + destination, destination], [
                    leaf({command: item.command + ':' + destination + ':normal', text: value},
                        'Keep the app’s layout', ['keep layout', 'default layout']),
                    leaf({command: item.command + ':' + destination + ':tile', text: value + ' and tile'},
                        'and tile with the other windows', ['and tile', 'tile'])
                ], value);
            choice.value = value;
            choice.optionalArguments = true;
            choice.description = 'Enter to open here · Tab for layout options';
            return choice;
        });
    }, base);
    node.value = base + ' in this workspace';
    node.optionalArguments = true;
    node.description = (item.description ? item.description + ' · ' : '')
        + 'Enter to open in this workspace · Tab for more arguments';
    return node;
}
function tileWorkspaceOptions(item, category) {
    var base = 'tile all ' + category;
    var node = branch(item.command, base,
        [base, 'tile open ' + category, 'tile ' + category, 'tile the ' + category].concat(item.forms || [], [item.text]),
        function() {
            var destinations = ['this workspace'];
            for (var n = 1; n <= 10; n++) destinations.push('workspace ' + n);
            return destinations.map(function(destination) {
                var row = leaf({command: item.command + ':' + destination, text: base + ' in ' + destination},
                    'in ' + destination, [destination]);
                row.description = destination === 'this workspace' ? 'Default · Enter to tile here' : 'Tile windows already in this workspace';
                return row;
            });
        }, base);
    node.tileWorkspace = true;
    node.clearInput = true;
    node.argumentPrompt = 'CHOOSE A WORKSPACE';
    node.categoryOrder = ['windows', 'terminals', 'browsers'].indexOf(category);
    return node;
}
function tilePairOptions(item) {
    var windows = item.tileWindows;
    var node = branch(item.command, 'tile two specific windows…', item.forms, function() {
        return windows.map(function(first) {
            var choice = branch(item.command + ':' + first.id, first.label, [first.label], function() {
                return windows.filter(function(second) { return second.id !== first.id; }).map(function(second) {
                    var row = leaf({command: item.command + ':' + first.id + ':' + second.id,
                        text: 'tile ' + first.label + ' and ' + second.label}, second.label, [second.label]);
                    row.description = 'Tile these two here · Other windows temporarily hidden';
                    return row;
                });
            }, 'tile ' + first.label + ' and');
            choice.clearInput = true;
            choice.description = 'Choose this first window, then a second';
            choice.argumentPrompt = 'CHOOSE THE SECOND WINDOW';
            return choice;
        });
    }, 'tile');
    node.clearInput = true;
    node.argumentPrompt = 'CHOOSE THE FIRST WINDOW';
    node.description = 'Choose two windows by name · Tile here and temporarily hide the others';
    node.categoryOrder = 4;
    return node;
}
function catalog(suggestions, dynamic, audio, files) {
    var root = [], moves = [], switches = [], monitor = null, namedMoves = [];
    var tileMonitors = {};
    var preciseVerbs = ['move', 'close', 'minimize', 'maximize', 'focus', 'show'];
    var hasWindowPicker = (dynamic || []).some(function(item) { return item.pickerWindow; });
    (suggestions || []).concat(dynamic || []).forEach(function(item) {
        if (/^apps:tile(?:$|-)/.test(item.command)) return;
        if (item.optionalOpen) { root.push(openOptions(item)); return; }
        if (item.tileWindows) { root.push(tilePairOptions(item)); return; }
        var listCategory = /^(windows|terminals|browsers):list$/.exec(item.command);
        if (listCategory) {
            var listLabel = 'list all ' + listCategory[1];
            var listRow = leaf(item, listLabel, [listLabel].concat(item.forms || [], [item.text]));
            listRow.categoryOrder = ['windows', 'terminals', 'browsers'].indexOf(listCategory[1]);
            root.push(listRow);
            return;
        }
        var tileMonitor = /^(windows|apps|browsers|terminals):tile-monitor:([1-9][0-9]*)$/.exec(item.command);
        if (tileMonitor) {
            var number = tileMonitor[2], category = tileMonitor[1];
            if (!tileMonitors[number]) tileMonitors[number] = [];
            var label = 'all ' + category;
            var form = 'tile ' + label + ' on monitor ' + number;
            var monitorRow = leaf(item, label, [form, 'tile open ' + category + ' on monitor ' + number].concat(item.forms || [], [item.text]));
            monitorRow.categoryOrder = ['windows', 'terminals', 'browsers', 'apps'].indexOf(category);
            tileMonitors[number].push(monitorRow);
            return;
        }
        var tileCategory = /^(windows|apps|browsers|terminals):tile$/.exec(item.command);
        if (tileCategory) {
            root.push(tileWorkspaceOptions(item, tileCategory[1]));
            return;
        }
        if (item.pickerWindow) {
            var node;
            if (item.destinations) {
                node = branch(item.command, item.text + ' to…', [item.text, item.text + ' to'], function() {
                    return item.destinations.map(function(destination) {
                        return leaf({command: item.command + ':' + destination.suffix,
                            text: item.text + ' to ' + destination.suffix}, destination.text,
                            [destination.text, destination.suffix]);
                    });
                }, item.text + ' to');
                node.workspacePrefix = item.text + ' to workspace ';
            } else node = leaf(item, item.text, item.forms);
            node.pickerWindow = true;
            root.push(node);
            return;
        }
        if (hasWindowPicker && preciseVerbs.indexOf(words(item.text)[0]) >= 0) return;
        var moving = /^window:move-workspace:([1-9][0-9]*)$/.exec(item.command);
        var switching = /^workspace:switch:([1-9][0-9]*)$/.exec(item.command);
        if (item.command === 'browser:prompt_website') return;
        if (moving || switching) {
            var number = (moving || switching)[1];
            var forms = [number];
            (item.forms || []).forEach(function(form) {
                var tail = /workspace (.+)$/.exec(form);
                if (tail && forms.indexOf(tail[1]) < 0) forms.push(tail[1]);
            });
            (moving ? moves : switches).push(leaf(item, number, forms));
        } else if (item.command === 'move:other_screen') {
            monitor = leaf(item, 'Other monitor', ['other monitor', 'other screen']);
        } else if (/^(move-app:|move-window:)/.test(item.command)) {
            namedMoves.push(item);
        } else root.push(leaf(item));
    });
    var monitorNumbers = Object.keys(tileMonitors).sort(function(a, b) { return Number(a) - Number(b); });
    if (monitorNumbers.length) {
        root.push(branch('tile-monitor', 'tile on monitor…', ['tile on monitor'],
            monitorNumbers.map(function(number) {
                return branch('tile-monitor:' + number, 'Monitor ' + number, ['monitor ' + number],
                    tileMonitors[number].sort(categoryCompare), 'tile on monitor ' + number);
            }), 'tile on monitor'));
    }
    var destinations = [];
    if (moves.length) destinations.push(branch('move-workspace', 'Workspace…',
        ['workspace'], moves, 'Move this window to workspace'));
    if (monitor) destinations.push(monitor);
    if (destinations.length) root.unshift(branch('move-window', 'Move this window to…',
        ['move', 'move window', 'move this window', 'move this window to', 'move the current window'],
        destinations, 'Move this window to'));
    namedMoves.forEach(function(item) {
        var suffix = / to (?:the )?other (?:screen|monitor|window)$/;
        var prefix = item.text.replace(suffix, '');
        if (prefix === item.text) { root.push(leaf(item)); return; }
        var workspaceId = 'named-workspace:' + item.command;
        var workspaceRows = function() { return moves.map(function(row) {
            return leaf({command: item.command + ':workspace:' + row.text,
                text: prefix + ' to workspace ' + row.text}, row.text, row.forms);
        }); };
        var workspaceBranch = branch(workspaceId, 'Workspace…', ['workspace'],
            workspaceRows, prefix + ' to workspace');
        workspaceBranch.workspacePrefix = prefix + ' to workspace ';
        var forms = (item.forms || [item.text]).map(function(form) { return form.replace(suffix, '') + ' to'; });
        forms.push(prefix);
        root.push(branch('named-move:' + item.command, prefix + ' to…', forms,
            [workspaceBranch, leaf(item, 'Other monitor', ['other monitor', 'other screen'])], prefix + ' to'));
    });
    if (switches.length) root.push(branch('switch-workspace', 'Switch to workspace…',
        ['switch', 'switch workspace', 'switch to workspace', 'go to workspace'],
        switches, 'Switch to workspace'));
    ['new', 'existing'].forEach(function(mode) {
        var text = 'Open website in ' + mode + ' browser…';
        root.push({id: 'website:' + mode, command: 'website:' + mode, text: text,
            forms: ['open website in ' + mode + ' browser', 'open web site in ' + mode + ' browser',
                'open a website in a ' + mode + ' browser', 'open a website in an ' + mode + ' browser',
                'open web site in an ' + mode + ' browser', 'open a ' + mode + ' browser to a website'],
            websiteMode: mode, matchWording: false});
    });
    ['output', 'input'].forEach(function(direction) {
        var noun = direction === 'output' ? 'audio output' : 'microphone';
        var state = (audio || {})[direction] || {};
        var node = branch('audio:' + direction, 'Switch ' + noun + '…',
            ['switch ' + noun, 'switch ' + noun + ' to'], function() {
                return (state.rows || []).map(function(device) {
                    var row = leaf({command: 'audio:' + direction + ':' + device.id, text: device.text},
                        device.label, [device.label, device.detail]);
                    row.audioChoice = {direction: direction, id: device.id};
                    row.description = (device.current ? 'Current default · ' : '') + device.detail;
                    return row;
                });
            }, 'Switch ' + noun + ' to');
        node.audioDirection = direction;
        root.push(node);
    });
    var fileNode = branch('files', 'Open file…', ['open file'], function() {
        return ((files || {}).rows || []).map(function(file) {
            var row = leaf({command: 'file:' + file.id, text: file.text}, file.label, [file.label, file.detail]);
            row.fileChoice = file.id;
            row.description = file.detail;
            return row;
        });
    }, 'Open file');
    fileNode.fileProvider = true;
    root.push(fileNode);
    return root;
}
function level(tree, path) {
    var children = tree, node = null;
    for (var i = 0; i < path.length; i++) {
        node = children.filter(function(row) { return row.id === path[i]; })[0];
        if (!node || !node.children) return {children: [], prefix: ''};
        children = childrenOf(node);
    }
    return {children: children, prefix: node ? node.prefix : '', workspacePrefix: node ? node.workspacePrefix : '',
        tileWorkspace: !!(node && node.tileWorkspace),
        argumentPrompt: node ? node.argumentPrompt : '',
        audioDirection: node ? node.audioDirection : '', fileProvider: !!(node && node.fileProvider),
        controlProvider: !!(node && node.controlProvider)};
}
function options(tree, path, query) {
    var current = level(tree, path);
    var rows = current.children.slice();
    if (current.tileWorkspace) {
        var number = /^(?:in\s+)?(?:workspace\s+)?([1-9][0-9]{0,8})$/.exec(query.trim());
        if (number && Number(number[1]) > 10)
            rows.push(leaf({command: current.prefix + ':' + number[1], text: current.prefix + ' in workspace ' + number[1]},
                'in workspace ' + number[1], ['workspace ' + number[1], number[1]]));
    }
    // Numeric move destinations use the existing parser's 1–9 digit rule.
    if ((path[path.length - 1] === 'move-workspace' || current.workspacePrefix) && /^[1-9][0-9]{0,8}$/.test(query.trim())) {
        var number = query.trim();
        if (!rows.some(function(row) { return row.text === number || row.text.toLowerCase() === 'workspace ' + number; }))
            rows.unshift(leaf({command: 'window:move-workspace:' + number,
                text: (current.workspacePrefix || 'move this window to workspace ') + number},
                current.workspacePrefix ? 'Workspace ' + number : number, [number, 'workspace ' + number]));
    }
    return rows;
}

// Prefix groups hold providers, not recursively expanded descendants.
function childrenOf(node) {
    if (typeof node.children !== 'function') return node.children || [];
    if (!node.cachedChildren) node.cachedChildren = node.children();
    return node.cachedChildren;
}
function words(text) {
    return String(text || '').replace(/…/g, '').trim().toLowerCase().split(/\s+/).filter(Boolean);
}
function withoutPrefix(form, count) { return words(form).slice(count).join(' '); }
function categoryCompare(a, b) {
    return (a.categoryOrder === undefined ? 100 : a.categoryOrder)
        - (b.categoryOrder === undefined ? 100 : b.categoryOrder);
}
// Only the first word defines a generic group. After that, preserve complete
// command chunks and their explicit argument providers; articles are not levels.
function grouped(entries) {
    var buckets = Object.create(null), order = [], seen = Object.create(null);
    entries.forEach(function(entry) {
        var verb = words(entry.text)[0];
        var identity = verb + ':' + entry.row.command;
        if (!verb || seen[identity]) return;
        seen[identity] = true;
        if (!buckets[verb]) { buckets[verb] = []; order.push(verb); }
        buckets[verb].push(entry);
    });
    return order.map(function(verb) {
        var items = buckets[verb];
        if (verb === 'tile' || verb === 'list') items.sort(function(a, b) {
            return categoryCompare(a.row, b.row);
        });
        var node = branch('prefix:' + verb, verb + '…', [verb], function() {
            return items.map(function(entry) {
                return Object.assign({}, entry.row, {
                    text: withoutPrefix(entry.text, 1) || 'Run ' + verb,
                    forms: entry.forms.map(function(form) { return withoutPrefix(form, 1); }),
                    matchWording: false
                });
            });
        }, verb);
        node.prefixGroup = true;
        node.verbGroup = true;
        node.prefixWords = verb;
        node.prefixForms = [verb];
        return node;
    });
}
function build(suggestions, dynamic, audio, files, controls) {
    var entries = [];
    catalog(suggestions, dynamic, audio, files).forEach(function(row) {
        var variants = [row.text].concat(row.forms || []), verbs = Object.create(null);
        variants.forEach(function(form) {
            var verb = words(form)[0];
            if (!row.pickerWindow && (dynamic || []).some(function(item) { return item.pickerWindow; })
                    && ['move', 'close', 'minimize', 'maximize', 'focus', 'show'].indexOf(verb) >= 0) return;
            if (!verb) return;
            if (!verbs[verb]) verbs[verb] = [];
            if (verbs[verb].indexOf(form) < 0) verbs[verb].push(form);
        });
        Object.keys(verbs).forEach(function(verb) {
            var forms = verbs[verb];
            var text = words(row.text)[0] === verb ? row.text : forms[0];
            var value = row.matchWording ? text.replace(/…/g, '') : row.value;
            entries.push({row: Object.assign({}, row, {value: value}), text: text, forms: forms});
        });
    });
    var preferred = ['open', 'minimize', 'maximize', 'move', 'close', 'list', 'tile', 'switch', 'focus', 'hide', 'show'];
    var roots = grouped(entries).filter(function(row) { return ['enable', 'disable', 'connect', 'disconnect'].indexOf(words(row.text)[0]) < 0; });
    ['enable', 'disable', 'connect', 'disconnect'].forEach(function(verb) {
        var node = branch('control:' + verb, verb + '…', [verb], function() {
            return ((controls || {}).rows || []).filter(function(row) { return row.verb === verb; }).map(function(item) {
                var row = leaf({command: 'control:' + item.id, text: item.text}, item.label, [item.label]);
                row.controlChoice = item.id;
                row.unavailable = !item.available;
                row.description = item.detail;
                return row;
            });
        }, verb);
        node.controlProvider = true;
        node.verbGroup = true;
        node.prefixWords = verb;
        roots.push(node);
    });
    return roots.sort(function(a, b) {
        var av = words(a.text)[0], bv = words(b.text)[0];
        var ai = preferred.indexOf(av), bi = preferred.indexOf(bv);
        if (ai < 0) ai = preferred.length;
        if (bi < 0) bi = preferred.length;
        return ai - bi || av.localeCompare(bv);
    });
}
function subsequence(target, query) {
    var j = 0;
    target = words(target).join(''); query = words(query).join('');
    for (var i = 0; i < target.length && j < query.length; i++) if (target[i] === query[j]) j++;
    return j === query.length;
}
// Consume only visible prefix words; leftover words belong to the next level.
function consumed(row, query) {
    var input = words(query), best = 0;
    (row.prefixForms || [row.prefixWords || row.text]).forEach(function(form) {
        var prefix = words(form), matched = 0;
        for (var i = 0; i < prefix.length && matched < input.length; i++)
            if (prefix[i].indexOf(input[matched]) >= 0) matched++;
        best = Math.max(best, matched);
    });
    return best;
}
// Search complete paths, even while displaying a shorter argument label.
function fullOption(row, prefix) {
    var forms = [row.text].concat(row.forms || []).map(function(form) {
        var clean = String(form).replace(/…/g, '').trim();
        var normalizedPrefix = words(prefix).join(' ');
        return !normalizedPrefix || words(clean).join(' ').indexOf(normalizedPrefix + ' ') === 0
            || words(clean).join(' ') === normalizedPrefix ? clean : prefix + ' ' + clean;
    });
    if (row.value) forms.push(row.value);
    return Object.assign({}, row, {forms: forms});
}
function matchesPath(row, query, depth) {
    if (row.tileWorkspace) {
        var category = row.prefix.split(' ').pop();
        if (new RegExp('^(?:tile\\s+)?(?:(?:all|open|the)\\s+)*' + category + '(?:\\s|$)', 'i').test(query.trim())) return true;
    }
    if (row.controlProvider && words(query)[0] === row.prefixWords) return true;
    if (row.fileProvider && /^open\s+file(?:\s|$)/i.test(query.trim())) return true;
    if ([row.text].concat(row.forms || []).some(function(form) { return subsequence(form, query); })) return true;
    if (!row.children || depth >= 32) return false;
    return childrenOf(row).some(function(child) {
        return matchesPath(fullOption(child, row.prefix || row.text.replace(/…/g, '')), query, depth + 1);
    });
}
function matching(rows, query) {
    if (!query.trim()) return rows.slice();
    // A short verb query should browse that verb before incidental descendant matches.
    var verbs = rows.filter(function(row) { return row.verbGroup && subsequence(row.text, query); });
    return verbs.length ? verbs : rows.filter(function(row) { return matchesPath(row, query, 0); });
}
function matchingLeaves(rows, query, prefix, depth) {
    if (depth >= 32) return [];
    var found = [];
    rows.forEach(function(raw) {
        var row = fullOption(raw, prefix);
        if (row.children) {
            found = found.concat(matchingLeaves(childrenOf(row), query, row.prefix || row.text, depth + 1));
        } else if (matchesPath(row, query, 0)) {
            found.push(Object.assign({}, row, {
                text: row.value || row.forms[0], matchWording: false
            }));
        }
    });
    return found;
}
function preview(tree, path, query, suppressed) {
    var currentPath = path.slice(), frames = [];
    for (var depth = 0; depth < 32; depth++) {
        var current = level(tree, currentPath);
        if (current.tileWorkspace) {
            // Category abbreviations have already selected this level. Only the
            // remaining words should search its workspace choices.
            var parts = words(query);
            if (parts[0] === 'tile') parts.shift();
            while (['all', 'the', 'open'].indexOf(parts[0]) >= 0) parts.shift();
            var category = current.prefix.split(' ').pop();
            // Compact category aliases (e.g. tileopenterminals) select the
            // workspace branch without leaving the alias as a destination query.
            if (new RegExp('^(?:tile)?(?:(?:all|the|open))*' + category + '$', 'i')
                    .test(parts.join(''))) {
                parts = [];
                query = '';
            }
            if (parts.length && subsequence(category, parts[0])) {
                parts.shift();
                query = parts.join(' ');
            }
        }
        // Keep custom numeric destinations available for both full and short input.
        var numeric = /(?:^|\s)([1-9][0-9]{0,8})$/.exec(query.trim());
        var all = options(tree, currentPath, numeric ? numeric[1] : query).map(function(row) {
            return fullOption(row, current.prefix);
        });
        var matches = matching(all, query);
        // A matching category label takes precedence over incidental matches
        // buried inside "two specific windows" or monitor choices.
        var directTile = matches.filter(function(option) {
            return [option.text].concat(option.forms || []).some(function(form) { return subsequence(form, query); });
        });
        if (directTile.some(function(option) { return option.tileWorkspace; })) matches = directTile;
        var exactTile = matches.filter(function(option) {
            return option.tileWorkspace && [option.text].concat(option.forms || []).some(function(form) {
                return words(form).join(' ') === words(query).join(' ');
            });
        });
        if (exactTile.length) matches = exactTile;
        if (current.tileWorkspace) {
            var numericQuery = /^(?:in\s+)?(?:workspace\s+)?(-?[0-9]+)$/.exec(query.trim());
            if (numericQuery) matches = all.filter(function(option) { return option.text === 'in workspace ' + numericQuery[1]; });
        }
        if (query.trim() && matches.length > 1 && matches.every(function(row) { return row.verbGroup; })
                && !matches.some(function(row) { return subsequence(row.text, query); })) {
            matches = matchingLeaves(matches, query, current.prefix, 0);
        }
        var row = matches.length === 1 ? matches[0] : null;
        var result = {path: currentPath, query: query, level: current,
            rows: matches, frames: frames, portal: null};
        // Website entry and explicit selection are never triggered by typing.
        if (suppressed || !query.trim() || !row || !row.children
                || ((row.optionalArguments || (row.clearInput && !row.tileWorkspace)) && [row.text].concat(row.forms || []).some(function(form) {
                    return subsequence(form, query);
                }))) return result;
        frames.push({path: currentPath.slice(), text: query, selection: 0, chosenPath: currentPath.concat([row.id])});
        currentPath = currentPath.concat([row.id]);
    }
    return result;
}

// Checkpoints remember navigation, never a consumed portion of the query.
function rememberedPreview(tree, path, query, suppressed, checkpoints) {
    var kept = [], currentPath = path.slice(), rewindCheckpoint = null;
    if (!suppressed) (checkpoints || []).some(function(checkpoint) {
        if (checkpoint.path.join('/') !== currentPath.join('/')) return true;
        if (query.length < checkpoint.text.length) { rewindCheckpoint = checkpoint; return true; }
        var parent = level(tree, currentPath);
        var id = checkpoint.chosenPath[checkpoint.chosenPath.length - 1];
        var row = parent.children.filter(function(option) { return option.id === id; })[0];
        if (!row || !matchesPath(fullOption(row, parent.prefix), query, 0)) return true;
        kept.push(checkpoint);
        currentPath = checkpoint.chosenPath.slice();
        return false;
    });
    var result = preview(tree, currentPath, query, suppressed || !!rewindCheckpoint);
    result.frames = kept.concat(result.frames);
    result.checkpoints = rewindCheckpoint ? kept.concat([rewindCheckpoint]) : result.frames;
    return result;
}
