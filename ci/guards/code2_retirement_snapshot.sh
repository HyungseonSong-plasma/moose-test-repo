#!/usr/bin/env bash
# code2 PR-A: read-only exact-HEAD FDEG evidence. No source retirement.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
head="$(git rev-parse HEAD)"
target=PhysicsFVElectronEnergyJouleHeating
out="$1"
if [ "$head" != "$EXPECTED_CODE2_HEAD" ]; then
  echo "CODE2_EXACT_HEAD_MISMATCH" >&2; exit 3
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "CODE2_TRACKED_WORKTREE_DIRTY" >&2; exit 4
fi
mkdir -p "$out"
set +e
python3 ci/guards/fdeg_structural.py --target "$target" --expected-head "$head" --output "$out/structural.json"
s_rc=$?
set -e
if [ "$s_rc" -ne 0 ] && [ "$s_rc" -ne 2 ]; then exit "$s_rc"; fi
test -s "$out/structural.json"
python3 ci/guards/fdeg_functional.py --target "$target" --structural "$out/structural.json" --expected-head "$head" --output "$out/functional.json"
python3 ci/guards/fdeg_transition.py --target "$target" --structural "$out/structural.json" --functional "$out/functional.json" --expected-head "$head" --output "$out/transition.json"
python3 - "$out" "$head" "$s_rc" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, head, s_rc = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
raw = {n: (out / (n + '.json')).read_bytes() for n in ('structural','functional','transition')}
s,f,t = (json.loads(raw[n]) for n in ('structural','functional','transition'))
target='PhysicsFVElectronEnergyJouleHeating'
assert [s['schema'],f['schema'],t['schema']] == ['fdeg.structural.v0.3','fdeg.functional.v0.2','fdeg.transition.v0.1']
assert all(d['target']==target for d in (s,f,t))
assert s['repository_head']==f['source_identity']['repository_head']==t['source_identity']['repository_head']==head
assert f['source_identity']['structural_graph_id']==t['source_identity']['structural_graph_id']==s['graph_id']
assert t['source_identity']['functional_graph_id']==f['graph_id']
assert t['safe_delete']=='HOLD' and t['caller_zero']=='NOT_PROVEN'
assert t['execution_status']=='NOT_EXECUTED' and t['plan_status']=='CONDITIONAL_PLAN'
assert all(x['eligible_to_execute'] is False for x in t['steps'])
summary={
 'schema':'code2.retirement_pra_snapshot.v0.1',
 'evidence_only':True,'target':target,'repository_head':head,
 'structural_return_code':s_rc,'structural_status':s['status'],
 'graph_ids':{n:d['graph_id'] for n,d in zip(raw,(s,f,t))},
 'report_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in raw.items()},
 'consumer_dispositions':[{k:v for k,v in c.items() if k in (
   'source_node','input_path','block_path','structural_edge_id','instance_id',
   'role','disposition','before','reference_scope')} for c in t['consumer_dispositions']],
 'change_sites':t['change_sites'],'protected_resources':t['protected_resources'],
 'blocking_obligations':[{k:v for k,v in b.items() if k in (
   'obligation_id','kind','gate','status','required_evidence','consumer')} for b in t['blocking_obligations']],
 'step_ids':[x['step_id'] for x in t['steps']],
 'caller_zero':t['caller_zero'],'runtime_observation':t['runtime_observation'],
 'numerical_equivalence':t['numerical_equivalence'],'safe_delete':t['safe_delete'],
 'limitations':['Static graph does not prove runtime activation or caller-zero',
                'Issue351 current-binary replay compatibility unapproved',
                'molar_eV generated mode invalid until explicitly classified']}
(out/'summary.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
print('CODE2_PR_A_GRAPH_CONSUMERS='+str(len(t['consumer_dispositions'])))
print('CODE2_PR_A_BLOCKERS='+str(len(t['blocking_obligations'])))
print('CODE2_PR_A_SAFE_DELETE='+t['safe_delete'])
PY
