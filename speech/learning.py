"""Reviewed exact-phrase grammar productions. Existing grammar always takes precedence."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from grammar_engine import normalize
from speech.storage import GRAMMAR
from speech import audit

PATH = GRAMMAR


def load(path=PATH):
    if not path.exists():return {'version':'initial','rules':[]}
    return json.loads(path.read_text())


def meaning(parsed):
    return [{k:c.get(k) for k in ('intent','canonical_plan','launch_options','interaction','requested_arguments')}
            for c in parsed.get('candidates',[])]


def validate(proposal, original, expected, grammar):
    if set(proposal)!={'kind','input_phrase','canonical_phrase','rationale'}:
        raise ValueError('Invalid rule fields')
    if proposal['kind'] not in ('phrase_rule','recognition_correction'):
        raise ValueError('Unsupported rule kind')
    source=proposal['input_phrase'];target=proposal['canonical_phrase']
    if not isinstance(source,str) or not isinstance(target,str) or not source.strip() or len(source)>2000 or len(target)>2000:
        raise ValueError('Invalid rule text')
    if normalize(source)!=normalize(original):raise ValueError('Rule changes the original input')
    if normalize(source)==normalize(target):raise ValueError('Rule does not change the phrase')
    base=getattr(grammar,'base',grammar)
    if base.parse(source)['status']!='unrecognized':raise ValueError('Rule would overlap existing grammar')
    parsed=base.parse(target)
    if parsed['status'] not in ('matched','needs_selection') or len(parsed['candidates'])!=1:
        raise ValueError('Rule target has no unique local parse')
    if meaning(parsed)!=meaning(expected):raise ValueError('Rule changes the proposed meaning')
    return parsed


def write(data,path):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    data['version']=uuid.uuid4().hex
    archive=path.parent/'grammar-versions';archive.mkdir(exist_ok=True,mode=0o700)
    content=json.dumps(data,indent=2)+'\n'
    snapshot=archive/(data['version']+'.json')
    with snapshot.open('x') as f:f.write(content)
    snapshot.chmod(0o600)
    temp=path.with_suffix('.tmp');temp.write_text(content);temp.chmod(0o600);temp.replace(path)


def approve(proposal,original,expected,grammar,observation_id,path=PATH):
    validate(proposal,original,expected,grammar)
    data=load(path)
    if any(r['enabled'] and normalize(r['input_phrase'])==normalize(original) for r in data['rules']):
        raise ValueError('An approved rule already covers this phrase')
    rule=dict(proposal,id=uuid.uuid4().hex,enabled=True,observation_id=observation_id,
              approved_at=datetime.now(timezone.utc).isoformat(),base_revision=getattr(grammar,'base',grammar).revision)
    before=data['version']
    audit.append('rule_approval_requested',{'rule':rule,'before_version':before,'validation':'passed'},observation_id)
    data['rules'].append(rule);write(data,path)
    audit.append('rule_activated',{'rule':rule,'before_version':before,'after_version':data['version']},observation_id)
    return rule


def disable(ident,path=PATH):
    data=load(path)
    for rule in data['rules']:
        if rule['id']==ident:
            before=data['version']
            audit.append('rule_disable_requested',{'rule_id':ident,'before_version':before},rule.get('observation_id'))
            rule['enabled']=False;write(data,path)
            audit.append('rule_disabled',{'rule_id':ident,'before_version':before,'after_version':data['version']},rule.get('observation_id'));return
    raise ValueError('Learned rule not found')


class LearnedGrammar:
    def __init__(self,base,path=PATH):
        self.base=base;self.learned=load(path)
        self.revision=hashlib.sha256((base.revision+self.learned['version']).encode()).hexdigest()

    def __getattr__(self,name):return getattr(self.base,name)

    def inventory(self):
        return self.base.inventory() | {'learned_grammar':self.learned}

    def parse(self,text):
        result=self.base.parse(text);result['grammar_revision']=self.revision
        if result['status']!='unrecognized':return result
        rules=[r for r in self.learned['rules'] if r['enabled'] and normalize(r['input_phrase'])==normalize(text)]
        if not rules:return result
        if len(rules)!=1:
            result['status']='ambiguous';return result
        rule=rules[0]
        parsed=deepcopy(self.base.parse(rule['canonical_phrase']))
        if parsed['status'] not in ('matched','needs_selection') or len(parsed['candidates'])!=1:
            result['reason']='Learned rule target no longer resolves uniquely.';return result
        parsed.update(transcript=text,normalized=normalize(text),grammar_revision=self.revision,
                      method='reviewed_phrase_rule',learned_rule_id=rule['id'],learned_rule_kind=rule['kind'],canonical_text=rule['canonical_phrase'])
        return parsed
