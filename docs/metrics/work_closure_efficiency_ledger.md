# Work Closure Efficiency Ledger

This ledger records user↔MOOSE interaction efficiency for CLOSED work items.

Metric definitions are canonical in `docs/guides/work_closure_validator.md`.

| Work ID | Title | Complexity | WCC | T-WCC | EVR | DBR | RWR | CLR | FBR | Reopened | Root-cause class | Primary process lesson |
|---|---|:---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---|---|
| M5-ion-wall | Solved-potential O2+ wall migration incident | C3 | pending | pending | pending | pending | pending | pending | pending | no | nonlinear convergence / scaling interaction | finalize after canonical promotion validation |

## Recording rules

- Add a row only when the work reaches formal `CLOSED` status.
- A row may remain `pending` while the designated baseline work is still open.
- Raw WCC is always retained even when complexity-normalized comparisons are later added.
- If historical counting is reconstructed rather than directly observed, suffix the value with `~` and explain the basis below the table.
- If a CLOSED work is later reopened, set `Reopened=yes`; its low WCC must not be treated as a clean efficiency success.

## Trend review

Once at least five CLOSED items exist in the same complexity class, review:

- median WCC;
- median EVR;
- RWR rate;
- FBR rate;
- reopened-work rate.

The desired trend is lower median WCC/EVR and RWR, with stable or improving closure quality and FBR.
