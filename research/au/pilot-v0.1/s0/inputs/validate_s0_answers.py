#!/usr/bin/env python3
"""Validate a manually or automatically produced AU S0 answer sheet (not scoring)."""
import argparse
import json
from pathlib import Path
from run_s0_model import validate

p = argparse.ArgumentParser()
p.add_argument('--prompts', type=Path, required=True)
p.add_argument('--answers', type=Path, required=True)
a = p.parse_args()
source = json.loads(a.prompts.read_text())
result = json.loads(a.answers.read_text())
print(json.dumps(validate(source['prompts'], result['answers']), indent=2))
