#!/usr/bin/env python3
"""Fail-closed P0 input validation of B+H02 versus B+H03."""
import argparse,math,re
from pathlib import Path

def run(text,arm):
    assert arm in ("H02","H03")
    assert text.count("    property_name = R_"+arm+"\n")==1
    other="H03" if arm=="H02" else "H02"
    assert "    property_name = R_"+other+"\n" not in text
    assert text.count("    variable = log_nm\n")==1
    assert text.count("    variable = "+("log_nop" if arm=="H02" else "log_ni")+"\n")==1
    assert text.count("    variable = w_O\n")==1
    assert text.count("    variable = p\n")==1
    assert "    variable = log_ne\n" not in text
    assert "    variable = log_energy\n" not in text
    assert "T_g_fixed" in text and "exp(lnm+lnp)" in text
    def coef(prop):
        pattern=r"property_name = "+re.escape(prop)+r"\n.*?expression = '(-?[0-9.eE+]+)\*R'"
        m=re.search(pattern,text,re.S)
        assert m,prop
        return float(m.group(1))
    count=2 if arm=="H02" else 3
    pm=0.016 if arm=="H02" else 0.032
    assert math.isclose(coef("S_O_mass_"+arm),count*0.016,rel_tol=1e-14)
    assert math.isclose(coef("S_neutral_mass_"+arm),count*0.016,rel_tol=1e-14)
    assert math.isclose(coef("S_Om_mass_"+arm),-0.016,rel_tol=1e-14)
    assert math.isclose(coef("S_Pos_mass_"+arm),-pm,rel_tol=1e-14)
    assert math.isclose(coef("S_O_mass_"+arm)+coef("S_Om_mass_"+arm)+coef("S_Pos_mass_"+arm),0,abs_tol=1e-14)
    print("B_PLUS_"+arm+"_EXCLUSIVE_MASS_CHARGE_P0_PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--overlay",type=Path,required=True)
    p.add_argument("--arm",choices=("H02","H03"),required=True)
    a=p.parse_args()
    run(a.overlay.read_text(),a.arm)
