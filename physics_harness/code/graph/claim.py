"""Evidence-backed, scoped assertions about graph subjects (design boundary).

A Claim asserts a predicate about one or more node/edge/resource subjects under
explicit conditions and scope; it is not the observation used to justify it.
Claim assessments may be supported, refuted, qualified, or unresolved by
multiple evidence references. Evidence links must preserve their roles and
cannot be treated as a simple count or automatic PASS gate.

A Claim may express conditional functionality, compatibility hypotheses, or
unfulfilled transition obligations. Actual execution, migration plans, and
approval gates belong to separate lifecycle components.

No Claim data class, validation, or assessment engine is implemented here.
"""
