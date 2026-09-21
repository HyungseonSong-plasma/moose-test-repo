# Branch cleanup provenance

Date: 2026-09-18

Policy:
- keep `main`;
- keep branches owned by currently open Issue #234;
- stale PRs #229, #238, and #244 were closed before cleanup because their owning issues are terminal;
- delete terminal-issue, probe, maintenance, temporary, and superseded branches;
- delete only when the live remote SHA exactly matches the pre-cleanup inventory.

The exact pre/post refs and deletion results are preserved in this directory.
