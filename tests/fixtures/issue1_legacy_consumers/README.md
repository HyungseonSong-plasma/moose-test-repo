# Issue #1 standalone diagnostic input fixtures

These are **byte-for-byte snapshots**, not regenerated or physics-updated inputs.
They preserve the two historical Issue #1 source decks independently for the
closed Issue #197 (H3 migration) and Issue #199 (H5 known-charge) diagnostic
runners. The original Issue #1 experiment inputs and closure evidence remain
unchanged in this change.

| Consumer | Former Issue #1 source | Snapshot Git blob SHA |
| --- | --- | --- |
| Issue #197 | `experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic/migration_only_exact_phi_ic.i` | `9906040c450e28b3f1de8628c3936cf3ad1dec74` |
| Issue #199 | `experiments/Issue1_reactor_o2plus_integration/poisson_analytic/poisson_analytic.i` | `5b20df8337828f74d40b122d2745310d46aa1b71` |

Source revision: `moose-test-repo/main@f6c4072c34143e3fb42bc9841eeac92eb138b058`.

The legacy `QPX*` names are **intentional** in these frozen decks.
The two existing diagnostic scripts replace only the required object types
when generating scratch `input.i` files. This move must not change input
constants, wall boundaries, runtime behavior, or evidence/acceptance meaning.

`tests/test_issue1_legacy_consumer_fixtures.py` checks exact snapshot bytes
by Git blob identity and ensures the callers use these standalone folders.
Full P2/P3 numerical replay is a separate validation gate.
