"""Deprecated root recipe compatibility namespace.

Canonical experiment intent lives in ``experiments/.../experiment.json`` and
reusable semantics live under specification/planning/execution/adapters and
other responsibility owners. New reusable behavior must not be added here.

This namespace has no semantic authority. It remains only for bounded historical
v1 protocol/reproduction callers until those callers are retired.
"""

COMPATIBILITY_ONLY = True
SEMANTIC_AUTHORITY_RETIRED = True
NEW_CALLERS_FORBIDDEN = True
REMOVAL_CONDITION = (
    "remove the root recipes namespace after all legacy v1 protocol and historical "
    "reproduction callers have been retired or migrated to canonical owners"
)
