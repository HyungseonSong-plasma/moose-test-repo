"""Self-tests for manifest builder and response format; no oracle needed."""
import json
import subprocess
from pathlib import Path

import pytest

import build_s0_prompts as build
from run_s0_model import parse_response, validate


def test_ast_extraction_includes_decorator_and_line_numbers():
    source = 'import dataclasses\n@dataclasses.dataclass\nclass Result:\n    flag: bool\n\ndef check():\n    return True\n'
    piece = build.prompt_segment(source, 'Result', __import__('ast').ClassDef)
    assert piece['start_line'] == 2 and piece['end_line'] == 4
    assert '   2: @dataclasses.dataclass' in piece['text']
    assert '   4:     flag: bool' in piece['text']


def test_response_validation_rejects_nonvisible_source_lines():
    prompts = [{'id': 'AU01', 'visible_source_lines': [1, 2, 3]}]
    ans = [{'id': 'AU01', 'answer': 'X', 'reason': 'test', 'source_lines': [2, 5]}]
    info = validate(prompts, ans)
    assert info['citation_range_checks']['AU01'] == {
        'valid_line_numbers': False, 'invalid_lines': [5]
    }
    assert info['complete']
    with pytest.raises(ValueError, match='Duplicate'):
        validate(prompts, ans + ans)


def test_parse_markdown_json():
    assert parse_response('```json\n{"id":"AU01"}\n```') == {'id': 'AU01'}
    with pytest.raises(ValueError):
        parse_response('[]')


def test_builder_gives_twelve_isolated_prompts_from_frozen_git(tmp_path, monkeypatch):
    root = tmp_path / 'r'
    root.mkdir()
    subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'AU Tester'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'au@test.invalid'], check=True)
    chunks = {
        'F01': 'def assess_finding(graph, claim):\n    return "HOLD"\n',
        'F02': 'class TargetCoverage:\n    @property\n    def global_consumer_closed(self):\n        return False\n\ndef analyze_target_coverage(graph, receipt, target_id):\n    return TargetCoverage()\n',
        'F03': 'def verify_dependencies(sources, contract):\n    return None\n',
        'F04': 'class VerificationReceipt:\n    @property\n    def semantic_compatibility_proven(self):\n        return False\n\ndef verify_generated_artifact(graph, receipt):\n    return VerificationReceipt()\n',
    }
    manifest = json.loads(Path(__file__).with_name('au_pilot_tasks_v01.json').read_text())
    expected = {}
    for meta in manifest['functions']:
        source = chunks[meta['id']].encode()
        f = root / meta['path']
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(source)
        expected[meta['path']] = build.blob_sha(source)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'fixtures'], check=True)
    rev = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    manifest['revision'] = rev
    m = tmp_path / 'manifest.json'
    m.write_text(json.dumps(manifest))
    monkeypatch.setattr(build, 'SOURCE_BLOBS', expected)
    out = tmp_path / 'prompts.json'
    report = build.build(m, root, out)
    assert report['prompts_built'] == 12
    assert report['source_files_verified'] == 4
    result = json.loads(out.read_text())
    assert len(set(x['id'] for x in result['prompts'])) == 12
    assert all('au_pilot_oracle' not in p['prompt'] for p in result['prompts'])
    assert all('QUESTION ID: ' + p['id'] in p['prompt'] for p in result['prompts'])
    assert all(p['visible_source_lines'] for p in result['prompts'])
    assert all(p['prompt_sha256'] == __import__('hashlib').sha256(p['prompt'].encode()).hexdigest()
               for p in result['prompts'])
