"""Compatibility facade for the Issue43 fast-plasma / Issue44 output runtime."""
from __future__ import annotations

import argparse

from . import issue43_fast_base as _base
from . import issue43_fast_characterization as _characterization
from . import issue43_fast_contract as _contract
from . import issue43_fast_orchestration as _orchestration
from . import issue43_fast_output_analysis as _output_analysis
from . import issue43_fast_output_contract as _output_contract
from . import issue43_fast_output_execution as _output_execution
from . import issue43_fast_v3_characterization as _v3_characterization

# Preserve the historical public/private module surface while moving ownership
# to focused semantic modules. Later owners intentionally override inherited
# aliases with the same object identities exposed by the historical monolith.
for _module in (
    _base,
    _contract,
    _v3_characterization,
    _output_contract,
    _output_analysis,
    _output_execution,
    _orchestration,
    _characterization,
):
    for _name in dir(_module):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_module, _name)


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output-preflight", action="store_true")
    parser.add_argument("--output-runtime-confirmation", action="store_true")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    known, _ = parser.parse_known_args(args)
    if known.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    if known.output_preflight:
        return _run_output_preflight(qpx=known.qpx, results_root=known.results_root)
    if known.output_runtime_confirmation:
        return _run_output_runtime_confirmation(
            qpx=known.qpx,
            results_root=known.results_root,
        )
    return _run_issue43_guarded(args)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
