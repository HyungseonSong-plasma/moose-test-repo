#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
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
    pat = re.compile(rf"(?ms)^  \\[{re.escape(name)}\\]\n.*?^  \\[\\]\n")
    matches = list(pat.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one block [{name}], found {len(matches)}")
    return matches[0].group(0)


def replace_child_block(text: str, name: str, new: str) -> str:
    old = child_block(text, name)
    return text.replace(old, new, 1)


def replace_line_in_child(text: str, name: str, old: str, new: str) -> str:
    body = child_block(text, name)
    if body.count(old) != 1:
        raise RuntimeError(f"[{name}] expected one token {old!r}, found {body.count(old)}")
    return text.replace(body, body.replace(old, new, 1), 1)


# Generate the production heavy parent first, then convert a private smoke copy.
runpy.run_path(str(PARENT_GENERATOR), run_name="__main__")
text = PARENT.read_text(encoding="utf-8")

# This smoke case tests the heavy formulation only; keep potential_fast at its
# zero initial value and remove the electron MultiApp/transfer coupling.
multi = text.find("[MultiApps]\n")
executioner = text.find("[Executioner]\n", multi)
if multi < 0 or executioner < 0:
    raise RuntimeError("generated parent coupling region not found")
text = text[:multi] + text[executioner:]

# eta_s = log[(Y_s/Y_O2)/(Y_s/Y_O2)_0].  All nonlinear composition coordinates
# therefore start from zero.  Om and Op use an effectively-zero positive floor.
for sp in SPECIES:
    old = child_block(text, f"w_{sp}")
    new = f"""  [eta_{sp}]
    type = INSFVScalarFieldVariable
    initial_condition = 0.0
    block = plasma
  []
"""
    text = text.replace(old, new, 1)

# Time derivatives of the independent eta coordinates and pressure.
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

# Softmax/simplex reconstruction with O2 as reference:
#   Y_O2 = 1 / (1 + sum r_s0 exp(eta_s))
#   Y_s  = r_s0 exp(eta_s) Y_O2
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

# Sigma = sum_s Y_s deta_s/dt.  Then dY_s/dt = Y_s(deta_s/dt-Sigma)
# and dY_O2/dt = -Y_O2 Sigma.
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

# For this O/O2 species set, Mn = 0.032/(1+A),
# A=Y_O+Y_Om+Y_Op+Y_Os.  The chain rule in eta coordinates is
# dA/dt=sum_atomic(Y_j deta_j/dt)-A*Sigma.
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
# The existing drho_dt_model = (Mn*dp/dt+p*dMn/dt)/(R*Tg) is already
# coordinate invariant and is intentionally retained.


def patch_transport(block_name: str, new_type: str, sp: str) -> None:
    global text
    body = child_block(text, block_name)
    body2 = re.sub(r"(?m)^    type = \\S+\n", f"    type = {new_type}\n", body, count=1)
    body2, n = re.subn(
        rf"(?m)^    variable = w_{re.escape(sp)}\n",
        f"    variable = eta_{sp}\n    mass_fraction = w_{sp}\n",
        body2,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"[{block_name}] variable replacement failed")
    text = text.replace(body, body2, 1)


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

# WCNSFVScalarFluxBC accepts a separate passive-scalar functor.  Apply its
# physical mass flux to the eta residual row while keeping reconstructed Y_s
# as the passive scalar.
for sp in SPECIES:
    text = replace_line_in_child(
        text, f"inlet_{sp}", f"    variable = w_{sp}\n", f"    variable = eta_{sp}\n"
    )

# O2+ wall loss is already expressed as a physical mass-flux functor.
text = replace_line_in_child(
    text,
    "O2p_migration_wall_loss",
    "    variable = w_O2p\n",
    "    variable = eta_O2p\n",
)

# One short fixed physical step is enough for this formulation smoke test.
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

# Strong formulation guards.
for sp in SPECIES:
    if re.search(rf"(?m)^  \\[w_{re.escape(sp)}\\]$", text):
        raise RuntimeError(f"raw solved heavy variable survived: w_{sp}")
    if f"variable = w_{sp}" in text:
        raise RuntimeError(f"raw heavy residual variable survived: w_{sp}")
    if f"property_name = w_{sp}" not in text:
        raise RuntimeError(f"physical simplex functor missing: w_{sp}")
    if f"variable = eta_{sp}" not in text:
        raise RuntimeError(f"log-ratio residual variable missing: eta_{sp}")

if "property_name = w_O2_constraint" not in text:
    raise RuntimeError("simplex reference O2 functor missing")
if "heavy_simplex_sigma_dot" not in text:
    raise RuntimeError("simplex time-chain-rule closure missing")
if "[MultiApps]" in text or "[Transfers]" in text:
    raise RuntimeError("smoke case still contains split coupling")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print("heavy log-ratio simplex smoke formulation ready")
