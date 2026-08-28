#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, math, os, re, sys
HERE=Path(__file__).resolve().parent
exp=json.loads((HERE/'expected.json').read_text())

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
fail=[]
for fn,key in [('qvt.msh','qvt_sha256'),('mesh.i','mesh_i_sha256'),('transport_data.txt','transport_data_sha256')]:
    p=HERE/fn
    if not p.is_file(): fail.append(f'missing {fn}')
    elif sha(p)!=exp[key]: fail.append(f'{fn} SHA mismatch')
# Rebuild exact input from fixed mesh.i + candidate physics.i
if (HERE/'mesh.i').is_file() and (HERE/'physics.i').is_file():
    (HERE/'input.i').write_bytes((HERE/'mesh.i').read_bytes()+b'\n'+(HERE/'physics.i').read_bytes())
if sha(HERE/'input.i')!=exp['input_sha256']:
    fail.append('rebuilt input.i SHA mismatch')
t=(HERE/'physics.i').read_text()
# Structural contract
required=[
 'type = QPXFVMassFractionAdvection','type = QPXFVMixtureAveragedDiffusion',
 'type = QPXThermalDiffusionMaterial','type = WCNSFVScalarFluxBC',
 "scalar_flux_pp = inlet_mdot_O2s", "scalar_flux_pp = inlet_mdot_O2p",
 "scalar_flux_pp = inlet_mdot_O", "scalar_flux_pp = inlet_mdot_Om",
 "scalar_flux_pp = inlet_mdot_Op", "scalar_flux_pp = inlet_mdot_Os",
 "expression = '1.0-s1-s2-s3-s4-s5-s6'",
 'rho = rho_mat','pressure = p',"direction = '-1 0 0'"
]
for tok in required:
    if tok not in t: fail.append('missing contract token: '+tok)
# There must be exactly six solved advection and diffusion kernels.
if t.count('type = QPXFVMassFractionAdvection') != 6:
    fail.append('expected exactly 6 QPXFVMassFractionAdvection kernels')
if t.count('type = QPXFVMixtureAveragedDiffusion') != 6:
    fail.append('expected exactly 6 QPXFVMixtureAveragedDiffusion kernels')
if t.count('type = WCNSFVScalarFluxBC') != 6:
    fail.append('expected exactly 6 WCNSFVScalarFluxBC inlet objects')
# Canonical #21 case must stay steady: transient accumulation is owned by #22.
if 'QPXFVMassFractionTimeDerivative' in t:
    fail.append('canonical #21 steady case must not contain transient species time derivative')
# ParsedFunctorMaterial reserves/automatically appends x,y,z,t.
# Reject custom aliases that collide with those parser symbols before QPX runs.
reserved_parser_symbols={'x','y','z','t','pi','e'}
for raw in re.findall(r"functor_symbols\s*=\s*'([^']+)'", t):
    aliases=raw.split()
    bad=reserved_parser_symbols.intersection(aliases)
    if bad:
        fail.append('reserved ADParsedFunctorMaterial symbol collision: '+','.join(sorted(bad)))
print('R21_PARSER_SYMBOL_STATIC_SELFTEST:',
      'PASS' if not any('reserved ADParsedFunctorMaterial symbol collision' in x for x in fail) else 'FAIL')

# Independent SCCM/species-flow identities.
Y=exp['inlet_mass_fractions']; s=sum(Y.values())
if abs(s-1.0)>1e-14: fail.append(f'inlet mass fractions sum to {s}')
M={'O2':.032,'O2s':.032,'O2p':.032,'O':.016,'Om':.016,'Op':.016,'Os':.016}
Mn=1.0/sum(Y[k]/M[k] for k in Y)
mdot=exp['Q_sccm']*1e-6/60*Mn/exp['Vm_std_m3_per_mol']
if abs(Mn-exp['mean_molar_mass_kg_per_mol'])/Mn>1e-14: fail.append('mean molar mass oracle mismatch')
if abs(mdot-exp['expected_total_mdot_kg_per_s'])/mdot>1e-14: fail.append('SCCM mdot oracle mismatch')
species_sum=sum(exp['expected_solved_species_mdot_kg_per_s'].values())
o2_remainder=mdot-species_sum
if abs(o2_remainder-Y['O2']*mdot)/mdot>1e-14: fail.append('constrained O2 inlet mass-flow remainder mismatch')
# Static mutation self-test: advection removal must be detectable.
mut=t.replace('type = QPXFVMassFractionAdvection','type = REMOVED_ADVECTION',1)
if mut.count('type = QPXFVMassFractionAdvection')==6:
    fail.append('advection static mutation self-test failed')
print('R21_SCCM_SPECIES_FLUX_SELFTEST:', 'PASS' if not any('oracle' in x or 'remainder' in x for x in fail) else 'FAIL')
print('R21_ADVECTION_STATIC_MUTATION_SELFTEST:', 'PASS' if mut.count('type = QPXFVMassFractionAdvection')==5 else 'FAIL')
if fail:
    print('R21_PREPARE: FAIL')
    for x in fail: print('  -',x)
    raise SystemExit(2)
print('R21_PREPARE: PASS')
