"""Context-scoped code graph relationships (reserved).

Hierarchy is expressed by directed PARENT_CHILD relations with a context:
(context_id, parent_node_id, child_node_id). Parents are not intrinsic node
properties. The same child may have distinct parents in different contexts.

Source ownership, execution reachability, and other views may project their
own parent-child hierarchies. Underlying semantic edges such as CALLS,
IMPORTS, or REFERENCES remain distinct: a call is not automatically a
parent-child claim. Static possibilities are not observed runtime activity.

No edge model or traversal is implemented in this scaffold.
"""
