"""#817 Code3 S5-R normalized electron-source and EI18/EI19 negative gates.

Only tests the original source ledger and exact one-block replacement.
Does not claim residual/AD parity or authorize source removal.
"""
from __future__ import annotations
import ast
import math
from experiments.Code3_electron_source_retirement import consumer_pairs as pairs
from experiments.Code3_electron_source_retirement import run as code3
from experiments.historical_recipe_support import issue192_s5r as s5r
from physics_harness.adapters.moose import parameters as mp

MATERIAL = "FunctorMaterials/s5r_electron_source"
KERNEL = "FVKernels/s5r_electron_source"
PROGRESS = (
    s5r.PROGRESS["EI01"], "electron_ionization_number_source",
    s5r.PROGRESS["EI20_O_IONIZATION"], s5r.PROGRESS["EDETACH_OM"],
    s5r.PROGRESS["H05_OM_O_DETACHMENT"],
)
SYMBOLS = ("rattach", "sei16", "rei20", "rdetach", "rh05")


def _scalar_expression(expression: str, variables: dict[str, float]) -> float:
    """Closed AST evaluator: arithmetic + named source symbols, no arbitrary calls."""
    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in SYMBOLS:
            return variables[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return (-1 if isinstance(node.op, ast.USub) else 1) * eval_node(node.operand)
        if isinstance(node, ast.BinOp):
            lhs, rhs = eval_node(node.left), eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return lhs + rhs
            if isinstance(node.op, ast.Sub):
                return lhs - rhs
            if isinstance(node.op, ast.Mult):
                return lhs * rhs
            if isinstance(node.op, ast.Div):
                if rhs == 0:
                    raise ValueError("ZERO_DIVISOR")
                return lhs / rhs
        raise ValueError("UNSUPPORTED_SOURCE_EXPRESSION_AST")
    result = eval_node(ast.parse(expression, mode="eval"))
    if not math.isfinite(result):
        raise ValueError("NONFINITE_SIGNED_ELECTRON_SOURCE")
    return result


def assert_s5r_electron_ledger(original: str, candidate: str) -> dict:
    path = pairs.S5R_TARGET
    if (code3._outside_target(original, path) !=
            code3._outside_target(candidate, path)):
        raise ValueError("NON_ELECTRON_INPUT_CHANGED")
    if (mp.get_parameter(original, path, "type") != code3.OLD or
            mp.get_parameter(candidate, path, "type") != code3.NEW):
        raise ValueError("ELECTRON_OWNER_TYPE_DRIFT")
    src = mp.words(mp.get_parameter(original, MATERIAL, "functor_names") or "")
    symbols = mp.words(mp.get_parameter(original, MATERIAL, "functor_symbols") or "")
    if src != list(PROGRESS) or symbols != list(SYMBOLS):
        raise ValueError("ELECTRON_IONIZATION_SOURCE_LEDGER_DRIFT")
    expr = mp.get_parameter(original, MATERIAL, "expression")
    if not expr or expr != mp.get_parameter(candidate, MATERIAL, "expression"):
        raise ValueError("ELECTRON_SIGNED_EXPRESSION_DRIFT")
    if (mp.get_parameter(original, path, "number_source") != "S_e_s5r" or
            mp.get_parameter(candidate, path, "v") != "S_e_s5r"):
        raise ValueError("SIGNED_SOURCE_FUNCTOR_BINDING_DRIFT")
    nref = float(mp.get_parameter(original, path, "n_ref"))
    coef = float(mp.get_parameter(candidate, path, "coef"))
    if not math.isfinite(nref) or nref <= 0 or not math.isclose(
            coef, 1.0 / nref, rel_tol=1e-15):
        raise ValueError("NORMALIZED_REFERENCE_COEF_DRIFT")
    for channel in ("EI18_O_TO_OS", "EI19"):
        if s5r.PROGRESS[channel] in src:
            raise ValueError("ENERGY_ONLY_CHANNEL_IN_ELECTRON_LEDGER")
        if channel == "EI18_O_TO_OS":
            st = s5r.HEAVY_STOICH[channel]
            if st != {"O": -1, "Os": 1}:
                raise ValueError("EI18_HEAVY_ATOM_LEDGER_DRIFT")
        else:
            if s5r.HEAVY_STOICH.get(channel) not in ({}, None):
                raise ValueError("EI19_NOT_ENERGY_ONLY")
        energy = "FVKernels/s5r_energy_" + channel.lower()
        if (mp.get_parameter(original, energy, "type") != "FVCoupledForce" or
                mp.get_parameter(original, energy, "v") != s5r.PROGRESS[channel] or
                not float(mp.get_parameter(original, energy, "coef")) < 0.0):
            raise ValueError("ENERGY_ONLY_CHEMISTRY_OWNER_DRIFT")
    controls = (
        {"rattach": 0., "sei16": 0., "rei20": 0., "rdetach": 0., "rh05": 0.},
        {"rattach": 2., "sei16": 0., "rei20": 0., "rdetach": 0., "rh05": 0.},
        {"rattach": 0., "sei16": 0., "rei20": 2., "rdetach": 0., "rh05": 0.},
        {"rattach": 0., "sei16": 5., "rei20": 0., "rdetach": 0., "rh05": 0.},
    )
    for values in controls:
        expected = s5r.AVOGADRO * (
            -values["rattach"] + values["rei20"] +
            values["rdetach"] + values["rh05"]) + values["sei16"]
        actual = _scalar_expression(expr, values)
        if not math.isclose(expected, actual, rel_tol=1e-15, abs_tol=1e-5):
            raise ValueError("ELECTRON_SOURCE_SIGN_OR_AVOGADRO_DRIFT")
    # EI18/EI19 are absent from the actual parsed signed Functor expression:
    # changing energy-only progress does not alter S_e_s5r.
    return {
        "normalized_n_ref_positive": True,
        "coefficient_exact_inverse": True,
        "electron_functor_count": len(src),
        "ei18_energy_only": True,
        "ei19_energy_only": True,
        "charge_and_energy_runtime": "NOT_MEASURED_HERE",
        "full_ad_jacobian": "NOT_MEASURED",
        "source_cut_allowed": False,
    }
