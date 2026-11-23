# Legacy Code Understandability Import Bridge

The canonical implementation was renamed to `libs.code_lucidity` in #769.

The old `libs.code_understandability` package and its `evaluation`,
`metrics`, and `model` submodules remain as import-only compatibility
bridges. They re-export canonical objects; they do not duplicate formulas
or own a second measurement implementation.

New code should import `libs.code_lucidity`. These shims protect the
previously tracked Python module entry points, but are **not** proof that
all external/dynamic consumers, serialized artifacts, or file-path users
have been inventoried. No automated rename/extraction is approved.
