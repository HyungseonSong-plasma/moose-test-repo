#!/usr/bin/env python3
"""Run S0 AU prompts as separate, isolated model requests; never read oracle data.

Supports OpenAI Chat Completions compatible endpoints including local models.
Model access is optional; --dry-run validates prompts without making requests.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import re
import sys


def parse_response(raw: str) -> dict:
    content = raw.strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError('Model response must be a JSON object')
    return result


def validate(prompts: list[dict], answers: list[dict]) -> dict:
    expected = {p['id']: p for p in prompts}
    if len(expected) != len(prompts):
        raise ValueError('Duplicate prompt ID')
    seen = set()
    citation_ranges = {}
    for ans in answers:
        if not isinstance(ans, dict) or ans.get('id') not in expected:
            raise ValueError('Unknown response task ID')
        ident = ans['id']
        if ident in seen:
            raise ValueError('Duplicate response ID: ' + ident)
        seen.add(ident)
        for field in ['answer', 'reason']:
            if not isinstance(ans.get(field), str):
                raise ValueError(f'{ident}: {field} must be a string')
        lines = ans.get('source_lines')
        if not isinstance(lines, list) or any(type(line) is not int for line in lines):
            raise ValueError(f'{ident}: source_lines must be a list of integers')
        legal_lines = set(expected[ident]['visible_source_lines'])
        invalid = sorted(set(lines) - legal_lines)
        citation_ranges[ident] = {'valid_line_numbers': not invalid, 'invalid_lines': invalid}
        c = ans.get('confidence')
        if c is not None and (type(c) not in (int, float) or not 0 <= c <= 1):
            raise ValueError(f'{ident}: confidence must be 0..1')
        if ans.get('abstained') is not None and type(ans['abstained']) is not bool:
            raise ValueError(f'{ident}: abstained must be bool')
    return {'expected': len(prompts), 'provided': len(answers),
            'complete': len(seen) == len(expected), 'missing': sorted(set(expected) - seen),
            'citation_range_checks': citation_ranges,
            'note': 'Line-in-range validity is not evidence that cited lines actually support the claim.'}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--prompts', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=Path('au_s0_answers_v01.json'))
    ap.add_argument('--model', default=None)
    ap.add_argument('--base-url', default=None, help='Optional local/OpenAI-compatible endpoint URL')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--max-tokens', type=int, default=512)
    args = ap.parse_args()
    data = json.loads(args.prompts.read_text(encoding='utf-8'))
    if data.get('schema') != 'au-s0-blind-prompts-v0.1':
        raise ValueError('Unsupported prompts manifest')
    prompts = data['prompts']
    if args.dry_run:
        result = validate(prompts, [])
        print(json.dumps({'dry_run': True, 'prompt_count': len(prompts),
                          'distinct_ids': len(set(p['id'] for p in prompts)),
                          'oracle_loaded': False}, indent=2))
        return 0
    if not args.model:
        raise ValueError('Model ID required unless --dry-run')
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('Install the openai Python SDK to run model requests') from exc
    # Local compatible servers often require a syntactic, but not valid, API key.
    local_endpoint = False
    if args.base_url:
        uri = urlparse(args.base_url)
        local_endpoint = uri.hostname in {'localhost', '127.0.0.1', '::1'}
    key = os.getenv('OPENAI_API_KEY') or ('local' if local_endpoint else None)
    if not key:
        raise RuntimeError('OPENAI_API_KEY is unset; no remote calls made')
    kwargs = {'api_key': key}
    if args.base_url:
        kwargs['base_url'] = args.base_url
    client = OpenAI(**kwargs)
    answers = []
    for item in prompts:
        # Each call has only a fixed system request and one isolated user prompt.
        # There is no conversation replay, shared context, oracle, or tests.
        resp = client.chat.completions.create(
            model=args.model, max_tokens=args.max_tokens,
            messages=[{'role': 'system', 'content': 'Answer source-code questions only from the displayed code. Output strict JSON.'},
                      {'role': 'user', 'content': item['prompt']}],
        )
        raw = resp.choices[0].message.content or ''
        try:
            ans = parse_response(raw)
            if ans.get('id') != item['id']:
                raise ValueError('Model response id mismatch')
        except (ValueError, json.JSONDecodeError) as e:
            ans = {'id': item['id'], 'answer': 'INVALID_RESPONSE', 'reason': str(e),
                   'source_lines': [], 'confidence': 0.0, 'abstained': True,
                   'raw_model_output': raw}
        answers.append(ans)
        # Checkpoint after each call to prevent loss on interruption.
        args.out.write_text(json.dumps({'schema': 'au-s0-answers-v0.1',
                                        'model': args.model, 'base_url': args.base_url,
                                        'revision': data['revision'],
                                        'prompt_hashes': {p['id']: p['prompt_sha256'] for p in prompts},
                                        'answers': answers}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{len(answers)}/{len(prompts)} {item["id"]} recorded')
    outcome = validate(prompts, answers)
    print(json.dumps({'run_complete': outcome['complete'], 'responses': len(answers),
                      'citation_numbers_in_displayed_source': all(v['valid_line_numbers'] for v in outcome['citation_range_checks'].values()),
                      'oracle_loaded': False}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
