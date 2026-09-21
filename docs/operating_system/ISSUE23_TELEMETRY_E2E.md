# Issue #23 telemetry consumer proof

This is an explicit, non-authoritative validation surface for `chatgpt-operation` Issue #23.
It does not change the repository's Paul operating-system binding, normal initialization,
scientific semantics, mutation authority, or acceptance truth.

The proof fetches exactly central revision
`268c0960253efaea3a99c9952fe9bf98885c57c4` and executes
`ci/issue23_telemetry_e2e.py` against that checkout. The script emits one logical
`state-refresh` activation plus a retry carrying the same `activation_id`; deterministic
aggregation must report one activation and one duplicate.

The consumer remains pinned to its existing Paul operating revision for normal operation.
Telemetry is never imported by `moose-test-init`, `session-bootstrap`, or `state-refresh`.
This isolated proof is loaded only when the Issue #23 validation command is explicitly run.

Manual validation command:

```bash
central_dir="$(mktemp -d)"
git -C "$central_dir" init -q
git -C "$central_dir" remote add origin https://github.com/HyungseonSong-plasma/chatgpt-operation.git
git -C "$central_dir" fetch --quiet --depth=1 origin 268c0960253efaea3a99c9952fe9bf98885c57c4
git -C "$central_dir" checkout --quiet FETCH_HEAD
python3 ci/issue23_telemetry_e2e.py "$central_dir"
```
