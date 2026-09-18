# Governed work manifests

New scientific experiments and refactor automation are data, not GitHub workflow files.

The reusable manifest schema, skeleton generator, runner, and evidence mechanics are centrally owned by:

`HyungseonSong-plasma/chatgpt-operation@4d5683b12be31e28b44bbe34723b02ae3493b172`

From an exact checkout of that revision, create a fail-closed skeleton with:

```bash
PYTHONPATH=src python3 -m chatgpt_operation.cli work new \
  --issue 253 --kind experiments --title "Gummel dt release"

PYTHONPATH=src python3 -m chatgpt_operation.cli work new \
  --issue 254 --kind refactor --title "Profile-step parser repair"
```

The generated identity is monotonic within an issue and kind, for example
`Issue_253_experiments01` or `Issue_254_refactor01`. Configure repository-relative,
argument-vector commands in the manifest.

GitHub execution is routed through the exact-SHA central `governed-work` action from
`.github/workflows/experiment.yml` and `.github/workflows/refactor.yml`. Nonzero exits,
timeouts, malformed manifests, identity mismatches, and incomplete execution fail closed and
produce `evidence.json`.
