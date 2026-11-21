#!/usr/bin/env python3
"""Build independent, oracle-free function-only AU prompts from a pinned Git commit."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

SOURCE_BLOBS = {
    'physics_harness/code/analysis/assessment.py': 'd50104fd02867e23ff82a9226d047e7e90594809',
    'physics_harness/code/analysis/impact.py': '6772dbef8a19813fbcb288e4195ea1631189e019',
    'physics_harness/code/verification/dependencies.py': '3b485bf11fe534bacb4b4931e254707942a0d837',
    'physics_harness/code/verification/consistency.py': '9ed800e45b4dfa3f75abf821643f008474900ad5',
}
CLASS_REQUIREMENTS = {'F02': ['TargetCoverage'], 'F04': ['VerificationReceipt']}


def git_show(repo: Path, revision: str, path: str) -> bytes:
    proc = subprocess.run(['git', '-C', str(repo), 'show', f'{revision}:{path}'],
                          capture_output=True, check=False)
    if proc.returncode:
        raise RuntimeError(f'Unable to read pinned {path} at {revision}: {proc.stderr.decode(errors="replace").strip()}')
    return proc.stdout


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()


def node_lines(source: str, symbol: str, kind: type[ast.AST]) -> tuple[int, int, list[str]]:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, kind) and getattr(n, 'name', None) == symbol]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one {symbol}, got {len(matches)}')
    node = matches[0]
    start = min([node.lineno] + [d.lineno for d in getattr(node, 'decorator_list', [])])
    end = node.end_lineno
    lines = source.splitlines()
    return start, end, lines[start - 1:end]


def prompt_segment(source: str, symbol: str, kind: type[ast.AST]) -> dict:
    start, end, lines = node_lines(source, symbol, kind)
    numbered = '\n'.join(f'{i + start:4}: {line}' for i, line in enumerate(lines))
    return {'symbol': symbol, 'start_line': start, 'end_line': end, 'text': numbered}


def build(manifest_path: Path, repo: Path, output: Path, seed: int = 7401) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    sources = {}
    for file in manifest['functions']:
        path = file['path']
        if path not in SOURCE_BLOBS:
            raise ValueError(f'Unapproved source file {path}')
        if path in sources:
            continue
        raw = git_show(repo, manifest['revision'], path)
        got_sha = blob_sha(raw)
        if got_sha != SOURCE_BLOBS[path]:
            raise ValueError(f'Pinned source blob mismatch: {path} expected={SOURCE_BLOBS[path]} actual={got_sha}')
        sources[path] = raw.decode('utf-8')

    funcs = {f['id']: f for f in manifest['functions']}
    tasks = manifest['tasks'][:]
    random.Random(seed).shuffle(tasks)
    prompts = []
    for task in tasks:
        f = funcs[task['function_id']]
        source = sources[f['path']]
        pieces = [prompt_segment(source, name, ast.ClassDef) for name in CLASS_REQUIREMENTS.get(f['id'], [])]
        body = prompt_segment(source, f['symbol'], (ast.FunctionDef, ast.AsyncFunctionDef))
        pieces.append(body)
        visible_lines = sorted({ln for piece in pieces for ln in range(piece['start_line'], piece['end_line'] + 1)})
        body_text = '\n\n'.join(piece['text'] for piece in pieces)
        prompt = (
            'You are answering ONE independent source-code comprehension question.\n'
            'Use ONLY the code printed below, with no external retrieval, tests, prior chats, or assumptions.\n'
            'An unshown dependency must remain unknown; distinguish explicit guarantees from guesses.\n'
            'Return ONLY a JSON object with keys: id, answer, reason, source_lines, confidence, abstained.\n'
            'answer must be a SHORT exact value (e.g. HOLD, False, 2); source_lines an array of visible code line numbers.\n'
            'confidence: float 0..1. abstained: boolean.\n'
            'If truly underdetermined, answer "ABSTAIN", explain briefly, and abstained=true.\n\n'
            f'Repository pinned SHA: {manifest["revision"]}\n'
            f'Source path: {f["path"]}\n'
            f'Target symbol: {f["symbol"]}\n\n'
            'SOURCE CODE (line numbers are part of the evidence):\n'
            f'{body_text}\n\n'
            f'QUESTION ID: {task["id"]}\n'
            f'QUESTION: {task["question"]}\n'
        )
        prompts.append({
            'id': task['id'], 'function_id': f['id'], 'domain': task['domain'],
            'question': task['question'], 'prompt': prompt,
            'source_path': f['path'], 'source_sha1_blob': SOURCE_BLOBS[f['path']],
            'visible_source_lines': visible_lines,
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
        })
    if len({p['id'] for p in prompts}) != len(prompts):
        raise ValueError('Duplicate task id')
    result = {
        'schema': 'au-s0-blind-prompts-v0.1', 'revision': manifest['revision'],
        'seed': seed, 'rules': 'one isolated model request per item; oracle never sent',
        'prompts': prompts,
    }
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return {'prompts_built': len(prompts), 'source_files_verified': len(sources),
            'output': str(output), 'seed': seed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-root', type=Path, required=True, help='Local git clone containing the pinned commit')
    ap.add_argument('--manifest', type=Path, default=Path(__file__).with_name('au_pilot_tasks_v01.json'))
    ap.add_argument('--out', type=Path, default=Path('au_s0_prompts_v01.json'))
    ap.add_argument('--seed', type=int, default=7401)
    args = ap.parse_args()
    info = build(args.manifest, args.repo_root, args.out, args.seed)
    print(json.dumps(info, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
