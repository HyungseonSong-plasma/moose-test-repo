# AU Research v0.1 — Source-grounded Comprehension Pilot

## Boundaries

AU means a model's ability to reconstruct exact code semantics, failures, dependencies and change impact from a fixed visible context. This pilot does **not** measure AU yet; it defines a reference set for a future blind run. The 12 questions cover 4 pinned repository functions; their answers are grounded in source. Source-derived oracles have **not** been independently executed as end-to-end fixtures.

## Model conditions

- **S0 Symbol:** provide only the requested function and minimal needed type/property definitions, not tests or answer key.
- **S1 Local:** also provide directly imported helpers and model definitions, with the retrieval budget logged.
- **S2 Repository:** controlled code search, with fixed file/tool budget; log all retrieved files and exact revision.
- Do not mix conditions in one chat that could leak previous answers. Fix model/version/settings and require citation to source lines; record uncertainty/abstention. Do not provide GitHub research issue discussion during a blind evaluation.

## Scoring and evidence

- **Semantic exact answer:** 0/1 per task, 12 total; no credit for confidently wrong answers. Accuracy by domain, not one arbitrary HU/AU score.
- **Evidence grounding:** independently grade whether cited code supports the stated conclusion. Correct guess without source reasoning is not equivalent to grounded understanding.
- **Uncertainty calibration:** record confidence and abstain for unsupported claims; ask to identify source-only limitations and downstream unknowns.
- **Change safety (phase 2):** controlled tiny edits, hidden behavioral tests, error/side-effect parity. Separate patch quality from reading comprehension.

## Notes

- Task manifest: `au_pilot_tasks_v01.json`. Independent sealed key: `au_pilot_oracle_v01.json` (do **not** send to evaluated model). The key should only be opened after an independent answer is submitted.
- Current phase is preparation only. No blind model attempts, model scoring, CI, production refactors, or external services were run.
- All candidate functions are from `HyungseonSong-plasma/moose-test-repo@2765d192f383d18dfe2c77dc100dfd66e23d3750`.
- Prior HU results 13/13 dispatch preference and 8/10 original nested-loop preference are **not AU ground truth**; they only nominate later style-ablation experiments.
