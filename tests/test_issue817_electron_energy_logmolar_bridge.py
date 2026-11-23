"""#817 source-locked present-MOOSE energy bridge for EI16 EI20 EDETACH.

Only the ElectronEnergyMaterial representation changes; physical n_e and
mean_en remain unchanged, as do reaction source and charge/energy owners.
"""
from __future__ import annotations
import unittest

from physics_app.ci import check_e8_ei16_energy_runtime as ei16
from physics_app.ci import check_stage5_ei20_runtime as ei20
from physics_app.ci import check_stage5_edetach_runtime as ed
from physics_harness.adapters.moose import parameters as mp

def accepted_bridge(text: str, prefix: str, material: str,
                    source_path: str, source_functor: str) -> None:
    parent="FunctorMaterials/"
    def val(block, key):
        return mp.get_parameter(text,parent+block,key)
    assert val(material,"type") == "ElectronEnergyMaterial"
    assert val(material,"state_form") == "log_molar_eV"
    assert val(material,"electron_density") == prefix+"_log_molar_density"
    assert val(material,"electron_energy_density") == prefix+"_log_molar_energy"
    for tag,var,symbol,expression in (
        ("density","n_e","ne","log(ne/6.02214076e23)"),
        ("energy","mean_en","energy","log(energy/6.02214076e23)"),
    ):
        block=prefix+"_log_molar_"+tag
        assert val(block,"type")=="ADParsedFunctorMaterial"
        assert val(block,"functor_names")==var
        assert mp.unquote(val(block,"functor_symbols"))==symbol
        assert mp.unquote(val(block,"expression"))==expression
    assert mp.get_parameter(text,source_path,"type")=="FVCoupledForce"
    assert mp.get_parameter(text,source_path,"v")==source_functor
    assert mp.get_parameter(text,source_path,"coef")=="1"
    assert mp.get_parameter(text,source_path,"number_source") is None
    assert "state_form=physical_eV" not in text and "state_form = physical_eV" not in text


class ActiveElectronEnergyBridgeTest(unittest.TestCase):
    def cases(self):
        return (
            (ei16.RUNTIME_INPUT,"ei16","mean_energy_bridge","FVKernels/n_e_source",
             "electron_ionization_number_source"),
            (ei20.runtime_input(),"ei20","mean_energy_bridge","FVKernels/n_e_source",
             "electron_ei20_number_source"),
            (ed.text(),"edetach","me","FVKernels/ns",
             "electron_edetach_number_source"),
        )

    def test_all_current_owners_migrated(self):
        for case in self.cases():
            with self.subTest(owner=case[1]):
                accepted_bridge(*case)

    def test_wrong_energy_representation_rejected(self):
        for text,tag,material,path,functor in self.cases():
            with self.subTest(owner=tag):
                malformed=mp.upsert_parameter(
                    text,"FunctorMaterials/"+material,"state_form","physical_eV")
                with self.assertRaises(AssertionError):
                    accepted_bridge(malformed,tag,material,path,functor)

    def test_wrong_signed_electron_functor_rejected(self):
        for text,tag,material,path,functor in self.cases():
            with self.subTest(owner=tag):
                malformed=mp.upsert_parameter(text,path,"v","R_wrong_sign")
                with self.assertRaises(AssertionError):
                    accepted_bridge(malformed,tag,material,path,functor)

    def test_wrong_normalization_in_one_bridge_rejected(self):
        for text,tag,material,path,functor in self.cases():
            with self.subTest(owner=tag):
                malformed=mp.upsert_parameter(
                    text,"FunctorMaterials/"+tag+"_log_molar_energy",
                    "expression","'log(energy/1.0e20)'")
                with self.assertRaises(AssertionError):
                    accepted_bridge(malformed,tag,material,path,functor)

if __name__=="__main__":
    unittest.main()
