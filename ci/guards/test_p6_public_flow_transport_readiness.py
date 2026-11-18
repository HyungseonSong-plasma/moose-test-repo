"""Fail-closed negative controls for P6-D1; model only, not Native P05."""
import copy
import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).with_name('p6_public_flow_transport_readiness.py')
spec = importlib.util.spec_from_file_location('gate', P)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

BASE = {"species": {s: {"charge_number": (-1 if s in ('e', 'Om') else 1)} for s in gate.CHARGED}}


def mk(data=None, *, manual=None, energy=False, old=False, auto=True):
    return gate.assess(data=BASE if data is None else data, selected=gate.CHARGED,
                       manual_owners=set(gate.CHARGED) if manual is None else set(manual),
                       physics_generates=auto, has_energy_action=energy,
                       manual_e_fluid_energy=True, legacy_ion_owners=old)


class TestContract(unittest.TestCase):
    def test_exact_git_blob_hash(self):
        self.assertEqual(gate.git_blob_sha1(b"test"),
                         "30d74d258442c7c65512eafab474568dd706c430")
        self.assertEqual(len(gate.PINNED_GIT_BLOBS),5)

    def test_public_d_baseline_missing_four(self):
        j=mk(old=True)
        self.assertEqual(j['missing_transport_species'], sorted(gate.CHARGED))
        self.assertEqual(len(j['overlapping_manual_and_generated']), 4)
        self.assertIn('P05_LEGACY_ION_FV_OWNERS_NOT_RETIRED',j['errors'])
        self.assertEqual(j['status'],'HOLD')

    def test_e_only_addition_rejected(self):
        d=copy.deepcopy(BASE); d['species']['e']['transport_coef']='lookup'
        self.assertEqual(mk(d)['missing_transport_species'],['O2p','Om','Op'])

    def test_json_only_addition_rejected(self):
        d=copy.deepcopy(BASE)
        for rec in d['species'].values():rec['transport_coef']='lookup'
        j=mk(d)
        self.assertNotIn('MISSING_TRANSPORT_JSON', j['errors'])
        self.assertIn('DUPLICATE_DDTRANSPORT_PRODUCER',j['errors'])

    def test_removing_all_manual_without_energy_rejected(self):
        d=copy.deepcopy(BASE)
        for rec in d['species'].values():rec['transport_coef']='lookup'
        j=mk(d, manual=[], old=False)
        self.assertEqual(j['errors'], ['ELECTRON_5_OVER_3_ENERGY_PROJECTION_NOT_PROVEN'])

    def test_energy_correction_alone_leaves_native_ion(self):
        d=copy.deepcopy(BASE)
        for rec in d['species'].values():rec['transport_coef']='lookup'
        j=mk(d,manual=[],energy=True,old=True)
        self.assertEqual(j['errors'], ['P05_LEGACY_ION_FV_OWNERS_NOT_RETIRED'])

    def test_source_ready_is_not_native_pass(self):
        d=copy.deepcopy(BASE)
        for rec in d['species'].values():rec['transport_coef']='lookup'
        j=mk(d,manual=[],energy=True,old=False)
        self.assertEqual(j['status'],'SOURCE_READY_NATIVE_NOT_RUN')
        self.assertEqual(j['native_p2'],'NOT_RUN')

    def test_missing_species_rejected(self):
        d=copy.deepcopy(BASE); del d['species']['e']
        with self.assertRaisesRegex(ValueError,'P6_D1_SPECIES_IDENTITY_CHANGED'):mk(d)

    def test_corrupt_species_charge_rejected(self):
        d=copy.deepcopy(BASE); d['species']['Om']['charge_number']='-' 
        with self.assertRaisesRegex(ValueError,'P6_D1_BAD_SPECIES_SCHEMA_Om'):mk(d)

    def test_manual_e_fluid_energy_not_lost(self):
        j=gate.assess(data=BASE,selected=gate.CHARGED,manual_owners={'e'},
                      physics_generates=True,has_energy_action=False,
                      manual_e_fluid_energy=False,legacy_ion_owners=False)
        self.assertIn('HISTORICAL_MANUAL_E_ENERGY_CLOSURE_MISSING',j['errors'])

    def test_overlay_selected_parsing(self):
        overlay="fem_species = 'e'\nfvm_species = 'O2p Om Op'\n"
        self.assertEqual(gate.selected_species(overlay),gate.CHARGED)
        for wrong in (overlay.replace('O2p','Op'),overlay.replace("'e'", "'O2p'"),
                      overlay.replace('fem_species','fvm_species')):
            with self.assertRaises(ValueError):gate.selected_species(wrong)

    def test_overlay_assignment_ast(self):
        self.assertEqual(gate.option_overlay('OVERLAY = "hello"\n'), 'hello')
        with self.assertRaises(ValueError):gate.option_overlay('A = "x"\n')

    def test_disabled_generators_not_false_pass(self):
        j=mk(auto=False,old=True)
        self.assertIn('MISSING_TRANSPORT_JSON',j['errors'])
        self.assertNotIn('DUPLICATE_DDTRANSPORT_PRODUCER',j['errors'])

if __name__=='__main__':unittest.main()
