#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
PARENT_GENERATOR = HERE / "prepare_heavy_parent.py"
PARENT = HERE / "heavy_parent.i"
OUT = HERE / "heavy_log_simplex_smoke.i"

SPECIES = ("O2s", "O2p", "O", "Om", "Op", "Os")
CHARGED = ("O2p", "Om", "Op")
STARTUP = {
    "O2": 0.7299241959504238,
    "O2s": 0.05,
    "O2p": 7.580404957618788e-5,
    "O": 0.1,
    "Om": 1.0e-30,
    "Op": 1.0e-30,
    "Os": 0.12,
}


def child_block(text: str, name: str) -> str:
    marker = f"  [{name}]\n"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"missing block [{name}]")
    if text.find(marker, start + len(marker)) >= 0:
        raise RuntimeError(f"duplicate block [{name}]")
    end_marker = "  []\n"
    end = text.find(end_marker, start + len(marker))
    if end < 0:
        raise RuntimeError(f"unterminated block [{name}]")
    return text[start : end + len(end_marker)]


def replace_child_block(text: str, name: str, new: str) -> str:
    old = child_block(text, name)
    return text.replace(old, new, 1)


def replace_line_in_child(text: str, name: str, old: str, new: str) -> str:
    body = child_block(text, name)
    if body.count(old) != 1:
        raise RuntimeError(f"[{name}] expected one token {old!r}, found {body.count(old)}")
    return text.replace(body, body.replace(old, new, 1), 1)


runpy.run_path(str(PARENT_GENERATOR), run_name="__main__")
text = PARENT.read_text(encoding="utf-8")

# Heavy-only smoke: retain potential_fast=0 and remove fast-plasma MultiApp coupling.
multi = text.find("[MultiApps]\n")
executioner = text.find("[Executioner]\n", multi)
if multi < 0 or executioner < 0:
    raise RuntimeError("generated parent coupling region not found")
text = text[:multi] + text[executioner:]

# eta_s = log[(Y_s/Y_O2)/(Y_s/Y_O2)_0].
for sp in SPECIES:
    old = child_block(text, f"w_{sp}")
    new = f"""  [eta_{sp}]
    type = INSFVScalarFieldVariable
    initial_condition = 0.0
    block = plasma
  []
"""
    text = text.replace(old, new, 1)

# Pressure and log-ratio coordinate time derivatives.
eta_props = " ".join(f"eta{sp}_state" for sp in SPECIES)
eta_values = " ".join(f"eta_{sp}" for sp in SPECIES)
aliases = f"""  [transient_state_dot_aliases]
    type = ADGenericFunctorMaterial
    prop_names = 'p_state {eta_props}'
    prop_values = 'p {eta_values}'
    define_dot_functors = true
    block = plasma
  []
"""
text = replace_child_block(text, "transient_state_dot_aliases", aliases)

# Exact simplex reconstruction, with an effectively-zero positive floor for
# initially absent Om and Op.
ratios = {sp: STARTUP[sp] / STARTUP["O2"] for sp in SPECIES}
den_terms = [f"{ratios[sp]:.17g}*exp(e{i})" for i, sp in enumerate(SPECIES)]
eta_names = " ".join(f"eta_{sp}" for sp in SPECIES)
eta_symbols = " ".join(f"e{i}" for i in range(len(SPECIES)))
simplex_blocks = f"""  [heavy_simplex_denominator]
    type = ADParsedFunctorMaterial
    property_name = heavy_simplex_den
    functor_names = '{eta_names}'
    functor_symbols = '{eta_symbols}'
    expression = '1.0+{"+".join(den_terms)}'
    block = plasma
  []
  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'heavy_simplex_den'
    functor_symbols = 'den'
    expression = '1.0/den'
    block = plasma
  []
"""
for sp in SPECIES:
    simplex_blocks += f"""  [simplex_w_{sp}]
    type = ADParsedFunctorMaterial
    property_name = w_{sp}
    functor_names = 'eta_{sp} heavy_simplex_den'
    functor_symbols = 'eta den'
    expression = '{ratios[sp]:.17g}*exp(eta)/den'
    block = plasma
  []
"""
text = replace_child_block(text, "O2_constraint", simplex_blocks)

# Sigma = sum_s Y_s * deta_s/dt.
dot_names = " ".join(f"deta{sp}_state_dt" for sp in SPECIES)
w_names = " ".join(f"w_{sp}" for sp in SPECIES)
w_symbols = " ".join(f"y{i}" for i in range(len(SPECIES)))
d_symbols = " ".join(f"d{i}" for i in range(len(SPECIES)))
sigma_expr = "+".join(f"y{i}*d{i}" for i in range(len(SPECIES)))
sigma_block = f"""  [heavy_simplex_sigma_dot]
    type = ADParsedFunctorMaterial
    property_name = heavy_simplex_sigma_dot
    functor_names = '{w_names} {dot_names}'
    functor_symbols = '{w_symbols} {d_symbols}'
    expression = '{sigma_expr}'
    block = plasma
  []
"""
if simplex_blocks not in text:
    raise RuntimeError("simplex insertion anchor missing")
text = text.replace(simplex_blocks, simplex_blocks + sigma_block, 1)

# Mn = 0.032/(1+A), A=Y_O+Y_Om+Y_Op+Y_Os.
# dA/dt = sum_atomic(Y_j*deta_j/dt) - A*Sigma.
dMn = """  [mean_molar_mass_dot]
    type = ADParsedFunctorMaterial
    property_name = dMn_dt_model
    functor_names = 'Mn_mix w_O w_Om w_Op w_Os detaO_state_dt detaOm_state_dt detaOp_state_dt detaOs_state_dt heavy_simplex_sigma_dot'
    functor_symbols = 'mnv yo yom yop yos deo deom deop deos sig'
    expression = '-31.25*mnv*mnv*(yo*deo+yom*deom+yop*deop+yos*deos-(yo+yom+yop+yos)*sig)'
    block = plasma
  []
"""
text = replace_child_block(text, "mean_molar_mass_dot", dMn)
# Existing drho_dt_model = (Mn*dp/dt + p*dMn/dt)/(R*Tg) is retained.


def patch_transport(block_name: str, new_type: str, sp: str) -> None:
    global text
    body = child_block(text, block_name)
    lines = body.splitlines(keepends=True)
    type_indices = [i for i, line in enumerate(lines) if line.startswith("    type = ")]
    if len(type_indices) != 1:
        raise RuntimeError(f"[{block_name}] expected one type line")
    lines[type_indices[0]] = f"    type = {new_type}\n"
    old_var = f"    variable = w_{sp}\n"
    if lines.count(old_var) != 1:
        raise RuntimeError(f"[{block_name}] expected one {old_var.strip()}")
    i = lines.index(old_var)
    lines[i : i + 1] = [
        f"    variable = eta_{sp}\n",
        f"    mass_fraction = w_{sp}\n",
    ]
    text = text.replace(body, "".join(lines), 1)


for sp in SPECIES:
    patch_transport(f"{sp}_time", "PhysicsFVLogMassFractionTimeDerivative", sp)
    patch_transport(f"{sp}_advection", "PhysicsFVLogMassFractionAdvection", sp)
    patch_transport(f"{sp}_diffusion", "PhysicsFVLogMixtureAveragedDiffusion", sp)
    patch_transport(
        f"{sp}_heavy_mass_em_correction",
        "PhysicsFVLogHeavyMassElectromigrationCorrection",
        sp,
    )

for sp in CHARGED:
    patch_transport(
        f"{sp}_electrostatic_drift",
        "PhysicsFVLogMassFractionElectrostaticDrift",
        sp,
    )

# Inlet BC: residual row is eta_s but passive scalar remains physical Y_s.
for sp in SPECIES:
    text = replace_line_in_child(
        text, f"inlet_{sp}", f"    variable = w_{sp}\n", f"    variable = eta_{sp}\n"
    )

# O2+ wall-loss functor already has physical mass-flux units.
text = replace_line_in_child(
    text,
    "O2p_migration_wall_loss",
    "    variable = w_O2p\n",
    "    variable = eta_O2p\n",
)

# One short fixed physical step.
old_exec = """  dt = 5.0e-9
  dtmin = 5.0e-9
  dtmax = 5.0e-9
  end_time = 2.0e-8
"""
new_exec = """  dt = 1.0e-10
  dtmin = 1.0e-10
  dtmax = 1.0e-10
  end_time = 1.0e-10
"""
if old_exec not in text:
    raise RuntimeError("heavy-parent executioner timing contract not found")
text = text.replace(old_exec, new_exec, 1)

# Formulation guards.
for sp in SPECIES:
    if f"  [w_{sp}]\n" in text:
        raise RuntimeError(f"raw solved heavy variable survived: w_{sp}")
    if f"    variable = w_{sp}\n" in text:
        raise RuntimeError(f"raw heavy residual variable survived: w_{sp}")
    if f"property_name = w_{sp}\n" not in text:
        raise RuntimeError(f"physical simplex functor missing: w_{sp}")
    if f"    variable = eta_{sp}\n" not in text:
        raise RuntimeError(f"log-ratio residual variable missing: eta_{sp}")

if "property_name = w_O2_constraint\n" not in text:
    raise RuntimeError("simplex reference O2 functor missing")
if "heavy_simplex_sigma_dot" not in text:
    raise RuntimeError("simplex time-chain-rule closure missing")
if "[MultiApps]" in text or "[Transfers]" in text:
    raise RuntimeError("smoke case still contains split coupling")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print("heavy log-ratio simplex smoke formulation ready")
