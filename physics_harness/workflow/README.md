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
