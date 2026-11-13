#!/usr/bin/env python3
"""Historical full-FEM contour generator retired with the grounded sheath BCs.

The original source is preserved in Git history / provenance archives. This
experiment must be explicitly redesigned with a supported electron wall law;
relabeling an old sheath implementation is not scientific parity.
"""


def build_case() -> str:
    raise RuntimeError(
        "RETIRED_GROUNDED_SHEATH_BCS: the historical full-FEM contour "
        "generator requires removed grounded sheath laws. Use a newly "
        "characterized wall law; do not substitute another BC implicitly."
    )


if __name__ == "__main__":
    build_case()
