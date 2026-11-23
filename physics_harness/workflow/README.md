# Physics workflow owner

This package is the sole owner of the repository's workflow profile registry, static generator, and (when explicitly authorized) case orchestration.

## Migration

The former `ci/workflow_harness.py`, `ci/workflow_profiles.json`, and `ci/workflow_templates/*` were moved here. Historical one-shot **definitions** remain byte-identical and profile-gated to avoid silently changing specialized scientific workflows. They are not generic reusable workflow templates.

`python -m physics_harness.workflow.profiles --self-test`
`python -m physics_harness.workflow.profiles --check`
`python -m physics_harness.workflow.profiles --generate`

The existing `Repository CI` output is still static and generated from `definitions/general-ci.yml`. The only intentional change to its bytes is updating the executable path for this module. Activation and authorization of costly specialized one-shot workflows are unchanged.

## Execution boundaries

Plan, render, and validate workflow configurations separately from dispatch. GitHub Actions workflow files must be registered and authorized before dispatch. No implicit approval, protected-rate transfer, scientific PASS, source HEAD mutation, or automatic full-100us run is granted by the workflow package.

## Case execution and profiles

`bin/physics.py workflow plan --spec experiments/.../case-workflow.json` and `matrix` are read-only. A case plan carries an exact source SHA, OCI digest, unique IDs, bounded timeout, and a maximum parallelism. `parallel_cases` creates one isolated matrix Job per case, `fail-fast: false`. `single_case` is the same case model with one ID. `general` keeps its existing repository-wide static CI policy.

`generate --spec ...` composes `templates/workflow.yml`, `job.yml` and `steps/{checkout,build,execute,artifacts}.yml` into a **new reviewable** YAML file. Generation requires two existing, reviewed script adapters (`build_script`, `case_script`) and **does not create or dispatch a GitHub run**. `--output .github/workflows/<name>.yml` writes only a new file, never overwrites a registered workflow.

The shared build is executed once; only ELF artifacts + a SHA/OCI/source manifest can be uploaded as the build closure. A matrix case downloads the same build closure, verifies every file's SHA, then runs its own case script in a private scratch directory and uploads a sanitized receipt. The case script interface is:

* `python build_script --output-dir DIR --source-sha SHA --oci-ref OCI`, producing a binary-only ELF closure
* `python case_script --case CASE --build-dir DIR --workspace PRIVATE_DIR --source-sha SHA --oci-ref OCI`, producing any scientific artifacts **only within the case's private scratch**

Generic `EXIT_ZERO_UNVERIFIED` means subprocess success alone: the full transient grid, conservation, and scientific equivalence remain **UNVERIFIED / HOLD**. Full 100µs authorization, protected EI staging, and scientific proof must be implemented and approved in the specific Physics case script; the orchestration layer does not grant them.

`dispatch --repository OWNER/REPO --workflow-file NAME.yml --ref APPROVED_BRANCH --authorize --spec ...` uses GitHub's API only for an **already registered active** workflow. It may fail for unregistered branch-only workflows. GitHub's dispatch API does not return a Run ID, so acceptance is not falsely reported as a completed Run. `status --repository ... --run-id ID` reads the actual Run/jobs. Credentials are read from `GH_TOKEN` or `GITHUB_TOKEN`; never from CLI arguments.

## First planned real-world candidate

`python bin/physics.py workflow plan --spec physics_harness/workflow/examples/issue652-g6b-publicd100-plan.json` produces an offline two-case plan with 417 and 941, original Public D 100-row source lineage, a 460-interval/100us **requested contract**, and a shared-build/independent-runner DAG. It has no `build_script` or `case_script`, so `generate` and `dispatch` deliberately fail closed until reviewed, case-specific P1/P2/P3 adapters exist. It does **not** authorize or run 100us.

Future generated workflows must be committed/reviewed and registered on GitHub before dispatch. The exact candidate source revision must also contain the required workflow entrypoint and reviewed adapter scripts; pinning an older Physics-only commit will not magically supply the orchestration code.

The generic workflow unit tests run in the unconditional `Repository CI` job, without adding `physics_harness/workflow/**` to the expensive Physics Code CI path filter.
