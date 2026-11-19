"""Context-independent graph node identity (v0.1 design boundary).

Nodes have stable identities within a source/revision identity contract, not
intrinsic parents. A node may be displayed under several parents or roots,
depending on context. Neither multiple parents nor cycles require new nodes.

Context-specific occurrences are not new canonical nodes. No implementation.
"""
