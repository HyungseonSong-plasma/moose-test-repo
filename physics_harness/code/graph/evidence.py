"""Source and observation provenance for graph facts (design boundary).

Evidence records *what was obtained*, how, where, and within which source or
runtime scope. The evidence item does not itself assert semantic equivalence,
approval, or a PASS/FAIL conclusion: those are scoped Claim assessments.

Keep distinct source-declared, inferred, observed, and unresolved provenance.
Multiple claims may cite one piece of evidence; a claim may use many evidence
items with different roles (supports, refutes, qualifies). Changing the
context view must never upgrade a static declaration into runtime observation.

No Evidence data class, collector, or validator is implemented here.
"""
