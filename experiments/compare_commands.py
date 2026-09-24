#!/usr/bin/env python3
"""Compare the fixed command pilot using local Qwen and OpenAI; never execute actions."""
import argparse
import datetime
import http.client
import json
import math
from pathlib import Path
import random
import statistics
import time

from qwen_commands import CASES, SYSTEM


def read_key(path):
    values = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, sep, value = line.partition('=')
        if sep and name.strip() == 'OPENAI_API_KEY':
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value)
    if len(values) != 1 or not values[0]:
        raise ValueError('Expected one nonempty OPENAI_API_KEY in credential file')
    return values[0]


def summarize(rows):
    times = sorted(row['seconds'] for row in rows)
    groups = {}
    for category in ('literal', 'paraphrase', 'reject'):
        subset = [r for r in rows if r['category'] == category]
        groups[category] = {'correct': sum(r['correct'] for r in subset), 'total': len(subset)}
    return dict(correct=sum(r['correct'] for r in rows), total=len(rows), groups=groups,
                median_seconds=statistics.median(times), mean_seconds=statistics.mean(times),
                p95_seconds=times[math.ceil(len(times)*0.95)-1], max_seconds=max(times),
                errors=sum('error' in r for r in rows),
                false_actions=sum(r['expected'] is None and isinstance(r.get('parsed'), dict)
                                  and r['parsed'].get('action') is not None for r in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path(__file__).resolve().parents[2] / '.env.local')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--include-local', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error('--repeats must be between 1 and 10')
    key = read_key(args.env_file)
    models = ['gpt-5.4-nano', 'gpt-5.4-mini']
    if args.include_local:
        models.insert(0, 'Qwen3.5-0.8B-Q4_0')
    connections = {m: (http.client.HTTPConnection('127.0.0.1', 18089, timeout=60)
                       if m.startswith('Qwen') else http.client.HTTPSConnection('api.openai.com', timeout=60))
                   for m in models}
    report = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  system_prompt=SYSTEM, repeats=args.repeats, temperature=0,
                  max_output_tokens=128, reasoning='off/none', structured_output_constraint=False,
                  transport='persistent http.client connection per model; sequential interleaved requests',
                  results={m: [] for m in models})
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        report['summary'] = {m: summarize(rows) for m, rows in report['results'].items() if rows}
        tmp = args.output.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(args.output)

    try:
        for repeat in range(args.repeats):
            cases = list(enumerate(CASES))
            random.Random(42 + repeat).shuffle(cases)
            for case_id, (category, utterance, expected) in cases:
                order = models[repeat % len(models):] + models[:repeat % len(models)]
                for model in order:
                    local = model.startswith('Qwen')
                    payload = dict(model=model, messages=[{'role': 'system', 'content': SYSTEM},
                                   {'role': 'user', 'content': utterance}], temperature=0)
                    if local:
                        payload.update(max_tokens=128, seed=42,
                                       chat_template_kwargs={'enable_thinking': False})
                    else:
                        payload.update(max_completion_tokens=128, reasoning_effort='none', store=False)
                    headers = {'Content-Type': 'application/json'}
                    if not local:
                        headers['Authorization'] = 'Bearer ' + key
                    body = json.dumps(payload).encode()
                    start = time.perf_counter()
                    connection = connections[model]
                    connection.request('POST', '/v1/chat/completions', body=body, headers=headers)
                    response = connection.getresponse()
                    raw_body = response.read()
                    seconds = time.perf_counter() - start
                    reply = json.loads(raw_body)
                    row = dict(repeat=repeat+1, case_id=case_id, category=category, input=utterance,
                               expected=expected, seconds=seconds, http_status=response.status, correct=False)
                    if response.status != 200:
                        error = reply.get('error', {})
                        row['error'] = {k: str(error.get(k, '')).replace(key, '[REDACTED]')
                                        for k in ('type', 'code', 'message')}
                        report['results'][model].append(row)
                        save()
                        raise RuntimeError(f'{model}: HTTP {response.status}: {row["error"]}')
                    choice = reply['choices'][0]
                    raw = choice['message'].get('content') or ''
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        parsed = None
                    row.update(raw=raw, parsed=parsed, finish_reason=choice['finish_reason'],
                               correct=parsed == {'action': expected} and choice['finish_reason'] == 'stop',
                               usage=reply.get('usage'), resolved_model=reply.get('model'),
                               service_tier=reply.get('service_tier'), request_id=response.getheader('x-request-id'))
                    report['results'][model].append(row)
                    save()
                    print(f'{model} run={repeat+1} case={case_id:02} {"PASS" if row["correct"] else "FAIL"} {seconds:.3f}s {raw}', flush=True)
    finally:
        for connection in connections.values():
            connection.close()
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
