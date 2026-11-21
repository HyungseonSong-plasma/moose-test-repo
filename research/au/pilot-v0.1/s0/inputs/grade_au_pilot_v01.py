"""Score structured AU v0.1 answers against a local sealed oracle.

Usage:
    python grade_au_pilot_v01.py candidate_answers.json

Candidate format:
    {"answers": [{"id": "AU01", "answer": "...", "reason": "...", "source_lines": [1]}]}

Answer accuracy is graded automatically. Evidence and explanation require
independent human/code review, not self-scored semantic similarity.
"""
import json
import pathlib
import sys


def canonical(value):
    return ' '.join(str(value).strip().lower().split())


def grade(candidate_path, oracle_path):
    results = json.loads(pathlib.Path(candidate_path).read_text(encoding='utf-8'))
    oracle = json.loads(pathlib.Path(oracle_path).read_text(encoding='utf-8'))
    if not isinstance(results, dict) or not isinstance(results.get('answers'), list):
        raise ValueError('Candidate must contain an answers list')
    actual = {}
    for item in results['answers']:
        if not isinstance(item, dict) or 'id' not in item:
            raise ValueError('Invalid answer entry')
        if item['id'] in actual:
            raise ValueError('Duplicate answer ID: ' + str(item['id']))
        actual[item['id']] = item
    expected = {item['id']: item for item in oracle['items']}
    if set(actual) - set(expected):
        raise ValueError('Unknown answer IDs: ' + ', '.join(sorted(set(actual) - set(expected))))
    grades = {}
    for ident, item in expected.items():
        submitted = actual.get(ident, {})
        grades[ident] = canonical(submitted.get('answer', '')) == canonical(item['answer'])
    return {'score': sum(grades.values()), 'maximum': len(grades),
            'exact_answer_accuracy': round(sum(grades.values()) / len(grades), 4),
            'by_task': grades,
            'not_graded': ['evidence-grounding validity', 'rationale quality',
                           'uncertainty calibration', 'edit correctness']}


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        raise SystemExit('Usage: python grade_au_pilot_v01.py ANSWERS.json [ORACLE.json]')
    local = pathlib.Path(__file__).with_name('au_pilot_oracle_v01.json')
    print(json.dumps(grade(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else local), indent=2))
