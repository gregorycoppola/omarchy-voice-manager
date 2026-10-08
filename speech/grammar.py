"""Bounded acyclic CFG with typed semantic actions; no fuzzy matching or execution.

Existing provider patterns become productions, not enumerated sentence matches.
Semantic constructors are Python-owned; language data cannot execute code.
"""
from dataclasses import asdict, replace
import json
import hashlib
from pathlib import Path
import re
import time
from command_catalog import RULES, WINDOW_RULES, INSTALLED_APP_RULES, VOCABULARY
from dataset_source import DATASET_REVISION, PROVIDER
from grammar_engine import Intent, Word, normalize
from ui_commands import OMARCHY_MENU_FORMS

SPEECH_PATTERNS = {
    'open_another_destination': (
        'open <destination> in a new tab',
        'open <destination> in another tab',
        'open a new tab for <destination>',
    ),
}

NUMBERS = dict(zip('one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(), map(str, range(1,21))))


def tokens(text):
    return normalize(text).split()


class Grammar:
    def __init__(self, context=None, apps=None, windows=None):
        self.context = context or {}
        self.vocabulary = dict(VOCABULARY)
        self.rules = []
        for rule in RULES:
            patterns = rule.patterns + SPEECH_PATTERNS.get(rule.id, ())
            forms = (*patterns, *(verb + pattern[4:] for pattern in patterns
                      if pattern.startswith('open ') for verb in ('launch', 'start')))
            self.rules.append(replace(rule, patterns=tuple(dict.fromkeys(forms))))
        self.apps = apps
        if windows is not None:
            from command_catalog import TERMINAL_CLASSES
            # Keep every matching terminal as a candidate; selection happens in
            # the dropdown, never by guessing which terminal the user meant.
            targets=getattr(windows,'targets',{})
            self.vocabulary['window'] = tuple(replace(w,forms=tuple(dict.fromkeys(
                (*w.forms,'terminal','the terminal'))))
                if targets.get(w.id,{}).get('class','').lower() in TERMINAL_CLASSES else w
                for w in windows.words)
            self.rules.extend(WINDOW_RULES)
        if apps is not None:
            self.vocabulary['installed_app'] = tuple(Word(a.desktop_id,a.name,a.forms) for a in apps.apps)
            self.rules.extend(INSTALLED_APP_RULES)
        # Correct spoken number forms are vocabulary, not ASR corrections.
        for name in ('workspace_number','monitor_number'):
            self.vocabulary[name] = tuple(Word(w.id,w.label,tuple(dict.fromkeys((*w.forms, *(n for n,v in NUMBERS.items() if v==w.id))))) for w in self.vocabulary.get(name,()))
        self.lexicon = {name: [(tokens(form),w.id) for w in words for form in w.forms]
                        for name,words in self.vocabulary.items()}
        self.lexicon['number'] = [(tokens(k),v) for k,v in NUMBERS.items()]
        self.lexicon['workspace_ref'] = [(tokens(x),'current') for x in ('this workspace','the current workspace','current workspace')]
        # Reusable nonterminals; tuples represent nonterminal references.
        self.productions = {
            'speech_destination': [('in', ('workspace_ref',)), ('in','workspace',('number',))],
            'tile_option': [('and','tile'), ('and','tile','it')],
            'open_verb': [('open',),('launch',),('start',)],
        }
        self.choices = []
        for rule in self.rules:
            for pattern in rule.patterns:
                seq = tuple((part[1:-1],) if re.fullmatch(r'<\w+>',part) else part for part in tokens(pattern))
                self.choices.append((rule,pattern,seq))
        self.revision=hashlib.sha256(json.dumps(self.inventory(),sort_keys=True).encode()+Path(__file__).read_bytes()).hexdigest()

    def match(self, seq, words, pos=0, bindings=None):
        """Match sequences and multiword lexical nonterminals without greedy slots."""
        self.work += 1
        if self.work > 100000:
            raise ValueError('Grammar work limit reached')
        bindings = bindings or {}
        if not seq:
            yield pos, bindings
            return
        first,*rest = seq
        if isinstance(first,str):
            if pos<len(words) and words[pos]==first:
                yield from self.match(rest,words,pos+1,bindings)
            return
        name=first[0]
        if name in self.productions:
            for production in self.productions[name]:
                for end,inner in self.match(production,words,pos,bindings):
                    yield from self.match(rest,words,end,inner)
            return
        entries=self.lexicon.get(name,())
        if name=='number' and pos<len(words) and re.fullmatch('[1-9][0-9]{0,8}',words[pos]):
            entries=[*entries,([words[pos]],words[pos])]
        for phrase,value in entries:
            if words[pos:pos+len(phrase)]==phrase and (name not in bindings or bindings[name]==value):
                yield from self.match(rest,words,pos+len(phrase),{**bindings,name:value})

    def full(self,seq,words):
        return [b for end,b in self.match(seq,words) if end==len(words)]

    @staticmethod
    def semantic(rule, bindings):
        args=tuple(sorted((k,bindings[v[1:]] if v.startswith('$') else v) for k,v in rule.arguments))
        intent=Intent(rule.intent_type,args)
        return dict(intent=intent.to_dict(), canonical_plan=intent.canonical_plan(),
                    command=rule.command.format(**bindings),rule=rule.id,bindings=bindings)

    def parse(self,text):
        started=time.perf_counter();self.work=0
        words=tokens(text)
        result={'transcript':text,'normalized':' '.join(words),'grammar_revision':self.revision,'dataset_revision':DATASET_REVISION,
                'method':'clean_grammar','candidates':[],'status':'unrecognized'}
        if not words or len(words)>100 or len(text)>2000:
            return {**result,'reason':'Speak one command, up to 100 words.'}
        found=[]
        try:
            # Installed app launches have the same precedence as the written picker.
            for dest in ((),(('speech_destination',),)):
                for tile in ((),(('tile_option',),)):
                    seq=(('open_verb',),('installed_app',))+dest+tile
                    for b in self.full(seq,words):
                        app=b['installed_app'];workspace=b.get('number',b.get('workspace_ref','current'))
                        intent=Intent('open_installed_app',(('desktop',app),))
                        found.append(dict(intent=intent.to_dict(),canonical_plan=intent.canonical_plan(),
                            command='desktop-app:'+app,rule='speech.open_with_options',bindings=b,
                            pattern='<open_verb> <installed_app> [<speech_destination>] [<tile_option>]',
                            launch_options={'workspace':workspace,'tile':bool(tile)},
                            argument_sources={'workspace':'explicit' if dest else 'default','tile':'explicit' if tile else 'default'},
                            resolved_workspace=(self.context.get('active',{}).get('workspace',{}).get('id') if workspace=='current' else int(workspace))))
            if not found:
                for rule,pattern,seq in self.choices:
                    for b in self.full(seq,words):
                        candidate=self.semantic(rule,b);candidate['pattern']=pattern;found.append(candidate)
            # Arbitrary positive workspace numbers, beyond the finite picker list.
            if not found:
                frames=[('switch to workspace <number>','switch_workspace'),('go to workspace <number>','switch_workspace'),
                        *[(p.replace('<workspace>','<number>'),r['intent_type']) for r in PROVIDER['numeric_rules'] for p in r['patterns']]]
                for pattern,kind in frames:
                    seq=tuple(('number',) if w=='<number>' else w for w in pattern.split())
                    for b in self.full(seq,words):
                        intent=Intent(kind,(('workspace',b['number']),))
                        found.append(dict(intent=intent.to_dict(),canonical_plan=intent.canonical_plan(),rule='speech.numeric',bindings=b))
            if not found:
                found.extend(self.additional(words,text))
        except ValueError as exc:
            return {**result,'reason':str(exc),'parse_ms':(time.perf_counter()-started)*1000}
        unique={}
        for item in found:
            key=json.dumps([item.get('canonical_plan'),item.get('launch_options'),item.get('interaction'),item.get('requested_arguments')],sort_keys=True)
            unique.setdefault(key,item)
        result['candidates']=list(unique.values())
        result['status']='matched' if len(unique)==1 else 'ambiguous' if unique else 'unrecognized'
        if len(unique)==1 and result['candidates'][0].get('launch_options',{}).get('workspace')=='current' and not result['candidates'][0].get('resolved_workspace'):
            result['status']='needs_context'
            result['reason']='The current workspace could not be resolved from the captured context.'
        if len(unique)==1 and result['candidates'][0].get('interaction'):
            result['status']='needs_selection'
        if not unique:result['reason']='No complete clean-grammar parse. Saved for review; no fuzzy correction or cloud request.'
        result['parse_ms']=(time.perf_counter()-started)*1000
        return result

    def additional(self,words,text):
        """Existing exact picker frames and explicit interaction entry points."""
        from picker_windows import parse as picker_parse
        found=[]
        parsed=picker_parse(text,self.context)
        if parsed:
            found.append(dict(intent=parsed.intent.to_dict(),canonical_plan=parsed.canonical_plan,rule='picker.window',command=parsed.command))
        # Bound generic app operations to known vocabulary rather than arbitrary text.
        for row in PROVIDER['free_text_rules']:
            if row.get('argument')!='application':continue
            for pattern in row['patterns']:
                for slot in ('installed_app','app','browser'):
                    seq=tuple((slot,) if w=='<application>' else w for w in pattern.split())
                    for b in self.full(seq,words):
                        value=b[slot];intent=Intent(row['intent_type'],(('application',value),))
                        found.append(dict(intent=intent.to_dict(),canonical_plan=intent.canonical_plan(),rule=row['id'],bindings=b))
        # Named window followed by more words; consume the destination exactly.
        for prefix in (('move',('window',),'to','workspace',('number',)),):
            for b in self.full(prefix,words):
                intent=Intent('move_named_window_workspace',(('window',b['window']),('workspace',b['number'])))
                found.append(dict(intent=intent.to_dict(),canonical_plan=intent.canonical_plan(),rule='speech.move_named_workspace',bindings=b))
        for category in ('windows','terminals','browsers','apps'):
            for lead in (('tile',category),('tile','all',category),('tile','the',category),('tile','all','the',category)):
                for b in self.full(lead+(('speech_destination',),),words):
                    intent=Intent('tile_workspace',(('category',category),('workspace',b.get('number','current'))))
                    found.append(dict(intent=intent.to_dict(),canonical_plan=intent.canonical_plan(),rule='speech.tile_workspace',bindings=b))
        # These picker-backed frames describe requested selections, never claim
        # that a device/file exists or that an executor target has been resolved.
        phrase=' '.join(words)
        for pattern,interaction in [
            (r'(enable|disable) (wi-fi|wifi|night light|bluetooth)', 'controls'),
            (r'(connect|disconnect) (.{1,120})', 'bluetooth_device'),
            (r'(switch audio output|switch microphone) to (.{1,120})', 'audio_device'),
            (r'(open file|find file|search files for) (.{1,160})', 'file'),
        ]:
            match=re.fullmatch(pattern,phrase)
            if match:
                found.append(dict(interaction=interaction,rule='interaction.'+interaction,
                                  requested_arguments=list(match.groups())))
        for interaction,forms in INTERACTIONS.items():
            if words in [tokens(p) for p in forms]:found.append(dict(interaction=interaction,rule='interaction.'+interaction))
        return found

    def inventory(self):
        return {'schema_version':1,'dataset_revision':DATASET_REVISION,'parser':'bounded acyclic CFG with lexical nonterminals',
                'rules':[asdict(r) for r in self.rules],
                'vocabulary':{k:[asdict(w) for w in v] for k,v in self.vocabulary.items()},
                'compositional_rules':self.productions,'interactions':INTERACTIONS,
                'speech_extensions':['installed app launch with optional destination and tiling','positive spoken workspace numbers one through twenty or digits',
                    'move named window to workspace','tile category in workspace','exact picker window and pair frames','known app list/show frames'],
                'limitations':['Interactive controls need selection; no invented complete action.',
                    'Arbitrary free text, dictation, and unknown entity names are unresolved.',
                    'No cloud fallback or learned corrections enabled.']}

INTERACTIONS={
 'browser_tabs':['focus tab','focus a tab','focus browser tab','focus on the browser tab','list tabs','list browser tabs','list all browser tabs'],
 'file':['open file','open a file','search files','find a file'],
 'audio_output':['switch audio output','choose audio output'],
 'microphone':['switch microphone','choose microphone'],
 'controls':['system controls','show system controls'],
 'website_new':['open website in new browser','open a website in a new browser'],
 'website_existing':['open website in existing browser','open a website in an existing browser'],
 'omarchy_menu':list(OMARCHY_MENU_FORMS),
}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',type=Path,help='Export static grammar inventory, with no private target names')
    parser.add_argument('--text',help='Parse one phrase with current desktop vocabulary, without execution')
    args=parser.parse_args()
    if args.export:
        args.export.write_text(json.dumps(Grammar().inventory(),indent=2)+'\n')
    if args.text:
        from installed_apps import discover_installed_apps
        from window_vocabulary import inject_windows
        from os_actions import capture_window_context
        context=capture_window_context() or {}
        grammar=Grammar(context,discover_installed_apps(for_picker=True),inject_windows(context))
        print(json.dumps(grammar.parse(args.text),indent=2))
