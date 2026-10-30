"""Research wall gamma=1 changes inherited BC material, never adds duplicate wall sink."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"experiments/Issue395_powered_chemistry_ladder/build_oxygen_24_wall_overlay.py"

def _load():
    s=importlib.util.spec_from_file_location("full24_wall",SCRIPT)
    m=importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m

def _sample():
    m=_load()
    species={"O":("w_O",.016,.2),"O2s":("w_O2s",.032,1.0),
             "Os":("w_Os",.016,.2)}
    blocks=[]
    bcs=[]
    for sp,(var,mass,gamma) in species.items():
        blocks.append(f"""  [stageb4_{sp}_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = stageb4_{sp}_surface_mass_flux
    functor_names = 'rho_neutral {var} T_g_fixed'
    functor_symbols = 'rho y tg'
    expression = '{gamma:.17g}*0.25*sqrt(8.0*8.31446*tg/(3.141592653589793*{mass}))*rho*y'
    block = plasma
  []""")
        bcs.append(f"""  [stageb4_{sp}_surface_loss]
    type = FVFunctorNeumannBC
    variable = {var}
    boundary = '{" ".join(m.WALLS)}'
    functor = stageb4_{sp}_surface_mass_flux
    factor = -1.0
  []""")
    return "\n[FunctorMaterials]\n" + "\n".join(blocks) + "\n[]\n" + \
           "[FVBCs]\n" + "\n".join(bcs) + "\n[]\n" + \
           "# ion_wall_number_flux negative_ion_wall_number_flux\n" + \
           "# atomic_positive_ion_wall_number_flux electron_wall_number_flux\n"

def test_reuses_existing_three_neutral_wall_bcs_and_sets_gamma1():
    m=_load()
    original=_sample()
    output=m.apply(original)
    assert len(re.findall(r"(?m)^    type = FVFunctorNeumannBC$",output))==3
    assert output.count("stageb4_O_surface_loss")==1
    assert output.count("stageb4_O2s_surface_loss")==1
    assert output.count("stageb4_Os_surface_loss")==1
    assert output.count("expression = '1.0*0.25*sqrt(")==3
    assert m.apply(output)==output

def test_wrong_wall_or_duplicate_material_is_refused():
    m=_load()
    with pytest.raises(ValueError,match="required existing"):
        m.apply(_sample().replace("stageb4_O_surface_flux","different_owner"))
    with pytest.raises(ValueError,match="missing wall"):
        m.apply(_sample().replace("plasma_focus_ring'","plasma_unknown'"))
    with pytest.raises(ValueError,match="wrong species"):
        m.apply(_sample().replace("variable = w_Os","variable = w_Om"))

def test_inlet_and_outlet_excluded():
    m=_load()
    with pytest.raises(ValueError,match="non-wall"):
        m.apply(_sample().replace("plasma_focus_ring'","plasma_focus_ring inlet'"))
