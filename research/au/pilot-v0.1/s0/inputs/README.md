# AU Pilot v0.1 — S0 Function-Only Blind Evaluation

**Status:** independent model evaluation not yet run. This package has no oracle and does not contain any scored answers. It contains a prompt builder, an isolated inference runner, and a format checker.

## Setup

Prepare a git clone of `HyungseonSong-plasma/moose-test-repo` containing commit `2765d192f383d18dfe2c77dc100dfd66e23d3750` (current checkout may differ). The prompt builder uses `git show` to read exactly that historical commit and verifies the four original Git blob hashes. No working-tree changes or GitHub write permissions are needed.

```bash
python build_s0_prompts.py --repo-root /path/to/moose-test-repo --out prompts.json
python run_s0_model.py --prompts prompts.json --dry-run
```

## Execute with an independent model

Requires a separate model endpoint **and may incur API costs**. Install the `openai` Python SDK. Use an API key supplied by the executor's own environment; do not paste API keys into ChatGPT or this repository.

```bash
python -m pip install openai
export OPENAI_API_KEY='...'  # supply locally; never commit
python run_s0_model.py --prompts prompts.json --model YOUR_MODEL --out answers.json
```

For a free/local OpenAI-compatible model server:

```bash
python run_s0_model.py --prompts prompts.json --model YOUR_LOCAL_MODEL \
    --base-url http://127.0.0.1:11434/v1 --out answers.json
```

The runner makes **12 isolated requests**. Each request receives only its own question and the pinned target function, plus a minimal result class when needed. It does not read or send tests, oracle data, earlier task answers, or repository discussion. No model service is configured or started by this package.

If using a separate AI chat manually, copy the content of **each individual** `prompts[*].prompt` into a **new independent chat** without the oracle or this research discussion. Save all results in the same `answers` structure. Do not use this current chat to self-evaluate; it has seen the sources and grading plan.

## After the run

```bash
python validate_s0_answers.py --prompts prompts.json --answers answers.json
python /path/to/grade_au_pilot_v01.py answers.json /private/path/to/au_pilot_oracle_v01.json
```

Keep `au_pilot_oracle_v01.json` **outside** this package and never include it in the model prompt, system message, retrieval sources, or uploaded model context. Existing grader computes exact-match correctness only. Source lines are mechanically validated as visible/non-visible by our format validator; whether a cited line *actually supports* the claim requires independent review. No subjective confidence-weighted AU score should be invented.

## Interpretation limits

- **Twelve questions on four functions**: a narrow, mostly deterministic smoke test; not a validated general AU metric.
- Same code repeated across three isolated tasks per function, but each model call has no answer history.
- Correct output accuracy can saturate; the next benchmark should include harder dependency, aliasing, exception, mutation, and ambiguity tasks.
- `S0` can answer only from the displayed function and necessary result class. `S1`/`S2` should be collected in truly separate, similarly isolated runs.
- Static-analysis predictions are not semantic equivalence proofs or permissions to change production code.
