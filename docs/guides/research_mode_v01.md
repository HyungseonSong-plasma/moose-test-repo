# Physics Harness Research Mode v0.1 — human goal clarification

**Status:** opt-in functionality; solver-independent. Scientific acceptance is not
changed by goal confirmation. This is *not* an automatic LLM analysis agent.

## Motivation

Receiving a scientific dataset does not uniquely define success. "Make the
electron density resemble HPEM" could mean lower whole-domain 2D error,
agreement on physically representative vertical/radial profiles, peak
position/width, or a combination. The operator, not the model, chooses which
evaluation boundary matters. Avoid cherry-picking only favourable slices.

Research Mode requires an explicit human decision *before* any analysis
dispatched through its own execution entrypoint. It does not modify the
existing simulation command or the SOL contract.

## Operator example

Start with an actual on-disk dataset (no data bytes copied into the session):

\`\`\`bash
python bin/physics.py research start HPEM_reference.csv --session experiment.research.json
\`\`\`

The persisted response is \`AWAITING_GOAL\` and asks the operator what to
investigate. When the operator states a goal without a precise evaluation
boundary:

\`\`\`bash
python bin/physics.py research goal experiment.research.json \
  --objective "Match the HPEM electron density distribution"
\`\`\`

This becomes \`AWAITING_SCOPE\`. The CLI returns a **single** next question
and presents these optional operator-selectable scopes:

| Scope | Meaning |
| --- | --- |
| \`full_field\` | Global 2D/3D/temporal comparison |
| \`representative_profiles\` | Predeclared scientifically meaningful slices |
| \`key_features\` | Peak magnitude, location, width, etc. |
| \`combined\` | Complementary evaluations |
| \`custom\` | Explicit operator-defined boundary (\`--scope-detail\` required) |

For example:

\`\`\`bash
python bin/physics.py research scope experiment.research.json \
  --scope representative_profiles
python bin/physics.py research status experiment.research.json
\`\`\`

This becomes \`AWAITING_CONFIRMATION\` and repeats the full stated objective
and scope for the operator. Explicit approval is a separate transition:

\`\`\`bash
python bin/physics.py research confirm experiment.research.json --approve
python bin/physics.py research check experiment.research.json
\`\`\`

Only now is the session \`GOAL_CONFIRMED\`, with a revision-matched
confirmation event. \`check\` returns a nonzero status if the goal is
unconfirmed or the dataset has changed since receipt.

An explicitly selected existing analysis can be routed through the gate:

\`\`\`bash
python bin/physics.py research execute experiment.research.json default-plot \
  --mode 2d-map --exodus plasma.e --input plasma.i \
  --time-us 100 --output profile.png
\`\`\`

Allowed commands currently: \`default-plot\`, \`oxygen-profile\`,
\`temporal-csv\`. The analysis implementation stays with the existing
command; no freeform shell, code execution, automatic simulation, or
scientific-policy invention.

If a goal is already precise, \`research goal ... --scope key_features\`
skips the extra clarification question, **but not human confirmation**.
A rejected proposed goal (\`confirm --reject\`) returns to the initial
question. A confirmed goal is immutable within the session.

## Reuse without silently inheriting approval

\`\`\`bash
python bin/physics.py research start next_run.csv \
  --session next_run.research.json --reuse-from experiment.research.json
\`\`\`

This proposes the previous confirmed goal/scope for the new dataset but
starts in \`AWAITING_CONFIRMATION\`, not \`GOAL_CONFIRMED\`. Explicit operator
approval is required again. The old session is unchanged.

## Machine contract

- \`physics_harness/specification/research_objective.py\` owns the
  solver-independent goal/scope vocabulary.
- \`physics_harness/application/research_session.py\` owns transitions,
  persistent JSON session, dataset SHA-256, revisioned confirmation evidence,
  reuse, next questions and fail-closed \`require_analysis_ready\` API.
- \`physics_harness/cli/commands/research.py\` performs argument routing.
- The \`physics_harness/cli/app.py\` canonical router exposes \`physics research\`.

State path:

\`\`\`text
DATA_RECEIVED -> AWAITING_GOAL
AWAITING_GOAL -> AWAITING_SCOPE (goal statement, no declared evaluation scope)
AWAITING_GOAL -> AWAITING_CONFIRMATION (goal statement + explicit scope)
AWAITING_SCOPE -> AWAITING_CONFIRMATION (scope supplied)
AWAITING_CONFIRMATION -> GOAL_CONFIRMED (explicit operator approval)
AWAITING_CONFIRMATION -> AWAITING_GOAL (rejection)
CONFIRMED goal A -> REUSE_PROPOSED goal B -> AWAITING_CONFIRMATION (new dataset)
\`\`\`

Each write validates the state and is persisted as an atomic JSON replacement.
The session records dataset path, size and SHA-256; goal and scope; revision;
transition events; and explicit confirmation marker. Goal confirmation is a
**permission to perform the scoped analysis**, not a scientific PASS, not a
simulation authorization, and not evidence that candidate data match a
reference.

## v0.1 boundaries

This mode **must be invoked explicitly**. It does not automatically detect
file uploads in ChatGPT or intercept all existing \`physics\` commands. Only
research-mode \`check\` / \`execute\` and library callers of
\`require_analysis_ready\` enforce this gate. A future host adapter can
invoke \`start\` when a dataset arrives and render the next question in chat.

The v0.1 scope vocabulary is a *human declaration*, not an automatic
assessment of which metric is scientifically best. Criteria such as sampling
coordinates, accepted RMSE thresholds and physical operating regions remain
future refinement tasks. The dataset SHA is checked but no cryptographic
authentication of the human user is provided by a local CLI; host identity
and authorization controls remain the caller's responsibility.

In particular, this mode does **not** change Oxygen14/HPEM coordinate,
timestamp, wall, or reaction-rate scientific acceptance limitations.
