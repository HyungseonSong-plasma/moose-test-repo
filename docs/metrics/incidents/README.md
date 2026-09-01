# Incident Metrics

This directory contains aggregated operational metrics derived from incident/root-cause reviews.

## Purpose

- Keep aggregate incident statistics separate from individual incident evidence in `docs/incidents/`.
- Preserve date-stamped snapshots so root-cause distribution can be compared over time.
- Support later trend analysis without rewriting historical observations.

## Structure

```text
docs/metrics/incidents/
├── README.md
└── snapshots/
    └── YYYY-MM-DD_root_cause_breakdown.md
```

## Recording rule

Each snapshot should preserve the reported category percentages and incident descriptors as observed on that date. Any regrouping or higher-level operational interpretation must be marked as derived analysis rather than source data.
