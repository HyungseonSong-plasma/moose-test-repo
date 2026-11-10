#!/usr/bin/env python3
"""Offline tests for the Issue #493 trusted-runner handoff. No Docker required."""
import csv
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

BASE = pathlib.Path(__file__).resolve().parent
SCRIPT = BASE / 'run_issue493.py'
SOURCE_ZIP = pathlib.Path(os.environ.get('ISSUE493_PACKAGE_ZIP', '/nonexistent/issue493-package.zip'))
spec = importlib.util.spec_from_file_location('run_issue493', SCRIPT)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class ExperimentTests(unittest.TestCase):
    @unittest.skipUnless(SOURCE_ZIP.is_file(), 'private user-Library package not staged on this runner')
    def test_immutable_package_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run.preflight(SOURCE_ZIP, pathlib.Path(temp) / 'extracted')
            self.assertEqual(result['preflight'], 'PASS')
            self.assertEqual(result['table_count'], 19)

    @unittest.skipUnless(SOURCE_ZIP.is_file(), 'private user-Library package not staged on this runner')
    def test_zip_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            modified = pathlib.Path(temp) / 'modified.zip'
            modified.write_bytes(SOURCE_ZIP.read_bytes() + b'tamper')
            with self.assertRaisesRegex(run.RunError, 'SHA-256 mismatch'):
                run.preflight(modified, pathlib.Path(temp) / 'extracted')

    def test_only_physics_utils_excluded_from_unity_with_vendor_cache_retained(self):
        import inspect
        source = inspect.getsource(run.build)
        self.assertIn('MOOSE_UNITY=true', source)
        self.assertIn('app_non_unity_dirs=/app/physics_app/src/utils', source)
        self.assertNotIn('MOOSE_UNITY=false', source)
        workflow = (pathlib.Path(__file__).resolve().parents[2] /
                    '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertIn('MOOSE_UNITY=true app_non_unity_dirs=/workspace/physics_app/src/utils', workflow)
        self.assertNotIn('make -j2 MOOSE_UNITY=false', workflow)
        self.assertIn('if (( jobs > 4 ))', workflow)

    def test_ci_nested_docker_shell_quotes_and_memory_probe(self):
        workflow = (pathlib.Path(__file__).resolve().parents[2] /
                    '.github/workflows/ci.yml').read_text(encoding='utf-8')
        job = workflow.split('  issue493-pr491-native-source-build:', 1)[1]
        marker = '-v "$PWD:/workspace" "$BUILD_BASE_REF" -lc ' + chr(39)
        self.assertEqual(job.count(marker), 1)
        payload = job.split(marker, 1)[1].split(
            '\n            ' + chr(39) + '\n', 1)[0]
        self.assertNotIn(chr(39), payload, 'nested single quote will break bash -lc')
        self.assertIn('while read -r mem_key mem_value mem_unit', payload)
        self.assertNotIn('awk /MemAvailable/', payload)
        self.assertIn('test "$mem_available_kb" -gt 0', payload)

    def test_docker_invocation_pins_image_and_research_controls(self):
        command = run.docker_cmd([(pathlib.Path('/tmp/example'), '/case', 'rw')], '/case', 'true')
        self.assertEqual(command[0], 'docker')
        self.assertIn(run.IMAGE, command)
        self.assertIn('OXYGEN_RESEARCH_400=1', command)
        self.assertIn('OXYGEN_RESEARCH_FULL24=0', command)

    def test_missing_native_time_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'truncated.csv'
            with path.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['time', 'mean_energy_max', 'ne_max'])
                writer.writerow(['0.0', '3.0', '4.0'])
            with self.assertRaisesRegex(run.RunError, '461'):
                run.verify_native_csv(path)

    def test_nonfinite_native_diagnostic_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / 'nonfinite.csv'
            with path.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['time', 'mean_energy_max'])
                for i in range(461):
                    writer.writerow([i / 460 * 0.0001, 'NaN' if i == 8 else '4.0'])
            with self.assertRaisesRegex(run.RunError, 'nonfinite'):
                run.verify_native_csv(path)

    @unittest.skipUnless(SOURCE_ZIP.is_file(), 'private user-Library package not staged on this runner')
    def test_four_staged_variants_have_correct_layer_order_and_five_rate_owners(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = pathlib.Path(temp)
            package = temp / 'extracted'
            run.preflight(SOURCE_ZIP, package)
            historical = temp / 'historical'
            mesh = historical / 'experiments/Issue395_powered_chemistry_ladder/baseline_plasma_plus_unstructured_cover_plus_wafer.msh'
            mesh.parent.mkdir(parents=True)
            mesh.write_text('STATIC-ONLY FIXTURE: NOT A REAL MESH')
            for case in ('417', '941'):
                for variant in run.VARIANTS:
                    workspace = temp / f'workspace_{case}_{variant}'
                    p = subprocess.run([sys.executable, str(package / 'scripts/stage_isolated_workspace.py'),
                                        '--prepared-source', str(historical), '--case', case,
                                        '--variant', variant, '--out-workspace', str(workspace)],
                                       check=True, capture_output=True, text=True)
                    out = json.loads(p.stdout)
                    self.assertEqual(len(out['input_arg']), 11 if variant == run.VARIANTS[0] else 12)
                    self.assertEqual(len(out['new_rate_files']), 5)
                    self.assertEqual({name.split('_')[0].split('-')[1] for name in out['new_rate_files']}, run.EXPECTED_IDS[case])
                    self.assertFalse((workspace / '.git').exists())
                    self.assertTrue((workspace / 'experiments/Issue395_powered_chemistry_ladder/private_rates').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)