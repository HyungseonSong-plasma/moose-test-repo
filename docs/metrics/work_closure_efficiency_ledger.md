# Work Closure Efficiency Ledger

This ledger records user↔MOOSE interaction efficiency for CLOSED work items.

Metric definitions are canonical in `docs/guides/work_closure_validator.md`.

| Work ID | Title | Complexity | WCC | T-WCC | EVR | DBR | RWR | CLR | FBR | Reopened | Root-cause class | Primary process lesson |
|---|---|:---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---|---|
| M5-ion-wall | Solved-potential O2+ wall migration incident | C3 | `>=20*` | `>=15*` | 8 | 5 | 2 | 0 known | no | no | nonlinear convergence / scaling interaction | parallelize hypothesis triage; include convergence sensitivity + numeric invariants in first batch |

`*` M5 predates Validator instrumentation. WCC and T-WCC are conservative lower bounds reconstructed from retained conversation/evidence and must not be treated as exact historical counts. EVR, DBR, and RWR were reconstructed from identifiable executed batches and rework events. See `docs/incidents/m5_closure.md` for the reconstruction basis.

## Recording rules

- Add a row only when the work reaches formal `CLOSED` status.
- Raw WCC is always retained even when complexity-normalized comparisons are later added.
- If historical counting is reconstructed rather than directly observed, mark the value and explain the basis below the table.
- If a CLOSED work is later reopened, set `Reopened=yes`; its low WCC must not be treated as a clean efficiency success.
- Lower-bound historical records such as M5 should be used for process lessons and directional comparison, not precise median calculations once instrumented exact records are available.

## M5 baseline interpretation

M5 is useful primarily as a process-debt baseline:

- `EVR = 8` is far above the future target because diagnostics were initially sequential;
- `DBR = 5` shows the first hypothesis/test matrix did not include enough high-information convergence discriminators;
- `RWR = 2` identifies delivery/checker defects that should be engineered to zero;
- `FBR = no` establishes the baseline from which first-batch resolution should improve.

Future comparable C3 incidents should aim for:

```text
RWR = 0
DBR <= 2
EVR <= 2 before root-cause/production-validation transition
FBR rate increasing over time
```

## Trend review

Once at least five CLOSED items exist in the same complexity class with exact instrumentation, review:

- median WCC;
- median EVR;
- RWR rate;
- FBR rate;
- reopened-work rate.

The desired trend is lower median WCC/EVR and RWR, with stable or improving closure quality and FBR.
