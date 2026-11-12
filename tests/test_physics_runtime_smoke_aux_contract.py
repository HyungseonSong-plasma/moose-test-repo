"""Keep the minimal Physics runtime smoke independent of retired custom AuxKernels.

This is an input/source contract. The immutable runtime-image smoke is a separate
execution gate and does not run the working-tree input until the image is rebuilt.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_uses_builtin_functor_aux_without_retired_density():
    deck = (ROOT / "physics_app/ci/smoke.i").read_text(encoding="utf-8")
    assert deck.count("[AuxKernels]") == 1
    assert deck.count("type = FunctorAux") == 1
    assert "functor = smoke_functor" in deck
    assert "variable = smoke_functor_value" in deck
    assert "type = ADGenericFunctorMaterial" in deck
    assert "prop_names = 'smoke_functor'" in deck
    assert "prop_values = '1.0'" in deck
    assert "type = Diffusion" in deck
    assert "type = Steady" in deck
    assert "PhysicsBackgroundDensity" not in deck
    for root, ext in (("src", "C"), ("include", "h")):
        assert not (ROOT / f"physics_app/{root}/auxkernels/PhysicsBackgroundDensity.{ext}").exists()
