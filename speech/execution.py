"""Convert a clean, unambiguous grammar result to an existing executor binding."""
from grammar_engine import Intent
from intent_matching import Candidate, ParseResult


def signature(parsed):
    if parsed['status'] not in ('matched','needs_selection') or len(parsed['candidates'])!=1:
        raise ValueError('Speech needs clarification; nothing was executed.')
    candidate=parsed['candidates'][0]
    return {k:candidate.get(k) for k in ('canonical_plan','launch_options','resolved_workspace','interaction','requested_arguments')}


def execution_result(parsed, window_labels=None):
    signature(parsed)
    c=parsed['candidates'][0]
    if c.get('interaction'):raise ValueError('This request needs the interactive picker.')
    data=c['intent'];args=data['arguments'];intent=Intent(data['type'],tuple(sorted(args.items())))
    if intent.canonical_plan()!=c['canonical_plan']:raise ValueError('Intent meaning changed.')
    command=c.get('command')
    if not command:
        kind=intent.type
        if kind=='switch_workspace':command='workspace:switch:'+args['workspace']
        elif kind=='move_window_workspace':command='window:move-workspace:'+args['workspace']
        elif kind=='move_named_window_workspace':command='move-window-workspace:'+args['window']+':'+args['workspace']
        elif kind=='tile_workspace':command=args['category']+':tile-workspace:'+args['workspace']
        elif kind in ('list_application','show_all_application'):
            command=('list-all:' if kind=='list_application' else 'show-all:')+args['application']
        else:raise ValueError('No installed executor binding for this grammar result.')
    label=intent.type.replace('_',' ').capitalize()
    if args:label+=' · '+', '.join(str((window_labels or {}).get(value,value)) for value in args.values())
    candidate=Candidate(command,intent,parsed['normalized'],1.0,'clean_grammar',label)
    return ParseResult(parsed['transcript'],'matched','exact',candidate,(candidate,),launch_options=c.get('launch_options'))
