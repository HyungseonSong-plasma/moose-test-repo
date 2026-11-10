#!/usr/bin/env python3
"""Run Issue493 S6 417/941 B,C via a restricted GitHub Actions secret handoff.

Consumes a 6-active-table input tar.xz from one protected Action secret, never
prints tables, and uploads only minimal non-sensitive status. No original private
rate secret is touched. An archive reference is restored from a prior public
GitHub Actions artifact at a pinned SHA. SCIENCE_HOLD always remains in force.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, pathlib, shutil, subprocess, sys, tarfile, tempfile, zipfile
from urllib import request

BASE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import run_issue493 as core

EXPECTED_TAR_SHA='f869620126ee0678491d62aa1f13902e745f26fe17190789bc6dae3bd51de256'
ARTIFACTS={
 '417':(13677089020,'72dfc15f31c82033c49650d619577739276bcadefe667da39e046a0e395d154f'),
 '941':(13677375813,'440b0358cf33331aa6de5e5d471f696d38bd303c10e77f5490c63fd423f91956'),
}
ACTIVE={'EI-401_O2_X.txt','EI-407_O2_X.txt','EI-415_O2_X.txt','EI-2069_O2_a1Delta.txt','EI-417_O2_X.txt','EI-941_O_3P.txt'}


def checked_unpack(archive:pathlib.Path,dest:pathlib.Path)->dict:
    if core.sha256(archive)!=EXPECTED_TAR_SHA:
        raise core.RunError('slim transport SHA mismatch')
    if dest.exists():
        raise core.RunError('non-empty target: refuse overwrite')
    dest.mkdir(parents=True,mode=0o700)
    with tarfile.open(archive,'r:xz') as tar:
        members=tar.getmembers()
        for item in members:
            path=(dest/item.name).resolve()
            if (not item.isfile() or not path.is_relative_to(dest.resolve()) or
                item.issym() or item.islnk() or not item.name.startswith((
                    'cases/', 'scripts/', 'new_rate_tables_moose_raw/')) and
                item.name!='experiment_manifest.json'):
                raise core.RunError('unsafe or unapproved tar member')
        tar.extractall(dest,filter='data')
    m=json.loads((dest/'experiment_manifest.json').read_text())
    if (m.get('schema')!='s6_newrate_partial_plasma_dsl_experiment_v1' or
        m.get('baseline_science_status')!='SCIENCE_HOLD' or
        m.get('new_tables_unit_transform')!='N_A * physical_m3_s' or
        m.get('table_count')!=19 or len(m.get('table_provenance',[]))!=19):
        raise core.RunError('immutable physics and rate contract mismatch')
    tables=dest/'new_rate_tables_moose_raw'
    if {x.name for x in tables.iterdir()}!=ACTIVE:
        raise core.RunError('wrong active table set')
    import math
    for record in m['table_provenance']:
        name=record['file']
        if name not in ACTIVE:continue
        p=tables/name
        if not p.is_file() or core.sha256(p)!=record['moose_sha256']:
            raise core.RunError('rate SHA mismatch: '+name)
        data=[]
        for line in p.read_text().splitlines():
            row=line.split()
            if len(row)!=2:raise core.RunError('malformed rate column: '+name)
            a,b=map(float,row)
            if not math.isfinite(a) or not math.isfinite(b) or b<0:
                raise core.RunError('non-finite or negative rate: '+name)
            data.append((a,b))
        if len(data)!=100 or any(data[j+1][0]<=data[j][0] for j in range(99)):
            raise core.RunError('rate grid must be 100 increasing rows: '+name)
        limits=record['mean_energy_range_eV']
        if abs(data[0][0]-limits[0])>1e-10 or abs(data[-1][0]-limits[1])>1e-10:
            raise core.RunError('out-of-contract energy domain: '+name)
    for case in ('417','941'):
        name=core.CASES[case]
        p=dest/'cases'/name
        order=json.loads((p/'input_order.json').read_text())
        if len(order)!=10 or len(set(order))!=10:
            raise core.RunError('bad input layer count: '+case)
        row=next(q for q in m['cases'] if q['case']==name)
        expected=set(row['active_replaced_lookup_files'])
        if len(expected)!=5:raise core.RunError('bad active owner count')
        for variant in core.VARIANTS:
            v=p/variant
            if set(q.name for q in v.glob('*.i')) != (set(order)|({'migrated_continuity.i'} if variant==core.VARIANTS[1] else set())):
                raise core.RunError('mismatched overlays: '+case+' '+variant)
            if {q.name for q in (v/'private_rates').glob('EI-*.txt')}!=expected:
                raise core.RunError('case active rate mismatch')
            for rate in expected:
                if core.sha256(v/'private_rates'/rate)!=core.sha256(tables/rate):
                    raise core.RunError('case rate SHA mismatch: '+rate)
        for inputfile in order[1:]:
            if core.sha256(p/core.VARIANTS[0]/inputfile)!=core.sha256(p/core.VARIANTS[1]/inputfile):
                raise core.RunError('unapproved overlay differences: '+inputfile)
        migration=next(v for v in m['migration_provenance'] if v['case']==case)
        if core.sha256(p/core.VARIANTS[1]/'migrated_continuity.i')!=migration['new_template_overlay_sha256']:
            raise core.RunError('continuity migration hash mismatch')
    return {'P0':'PASS','science':'HOLD','package_sha256':EXPECTED_TAR_SHA,
            'rate_tables_present':6,'cases':['417','941'],'native_P2':'NOT_RUN'}


def restore_archive(case:str,token:str,pkg:pathlib.Path, local_zip:pathlib.Path|None=None)->str:
    case_name=core.CASES[case]
    artifact,expected=ARTIFACTS[case]
    path=pkg/'archived_reference'/case_name/'plasma.csv'
    path.parent.mkdir(parents=True,exist_ok=True)
    outer=f'issue477_s6_combined_consumers/{case_name}/run/plasma.csv'
    if local_zip is None:
        if not token:raise core.RunError('Actions read token missing')
        url=f'https://api.github.com/repos/HyungseonSong-plasma/moose-test-repo/actions/artifacts/{artifact}/zip'
        req=request.Request(url,headers={'Accept':'application/vnd.github+json',
                                        'Authorization':'Bearer '+token,
                                        'X-GitHub-Api-Version':'2022-11-28'})
        target=pkg/f'artifact_{case}.zip'
        with request.urlopen(req,timeout=180) as response,target.open('wb') as out:
            shutil.copyfileobj(response,out)
    else:
        target=local_zip
    with zipfile.ZipFile(target) as z:
        with z.open(outer) as src,path.open('wb') as out:shutil.copyfileobj(src,out)
    if local_zip is None:target.unlink()
    if core.sha256(path)!=expected:raise core.RunError('archived reference SHA mismatch')
    core.verify_native_csv(path)
    return expected


def main()->int:
    os.umask(0o077)
    p=argparse.ArgumentParser()
    p.add_argument('--package-tar',type=pathlib.Path,required=True)
    p.add_argument('--case',choices=('417','941'),required=True)
    p.add_argument('--output',type=pathlib.Path,required=True)
    p.add_argument('--candidate',type=pathlib.Path)
    p.add_argument('--historical',type=pathlib.Path)
    p.add_argument('--mode',choices=('preflight','run'),default='preflight')
    p.add_argument('--reference-artifact-zip',type=pathlib.Path)
    p.add_argument('--timeout-seconds',type=int,default=19800)
    opts=p.parse_args()
    opts.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    status={'science':'HOLD','case':opts.case,'P0':'NOT_RUN','P1':'NOT_RUN','P2':'NOT_RUN','P3':'NOT_RUN','P4':'NOT_RUN'}
    try:
        pkg=opts.output/'verified_package'
        status.update(checked_unpack(opts.package_tar,pkg))
        archive_hash=restore_archive(opts.case,os.environ.get('GITHUB_TOKEN',''),pkg,opts.reference_artifact_zip)
        status['archive_sha256']=archive_hash
        if opts.mode=='run':
            if not opts.candidate or not opts.historical:raise core.RunError('run requires candidate and historical')
            candidate,historical=opts.candidate.resolve(),opts.historical.resolve()
            if core.git_head(candidate)!=core.CANDIDATE_SHA or core.git_head(historical)!=core.HISTORICAL_SHA:
                raise core.RunError('source checkout pin failed')
            if shutil.which('docker') is None:raise core.RunError('Docker unavailable on runner')
            core.run_step(['docker','pull',core.IMAGE],opts.output/'P1_pull.log',1800)
            binary,binary_sha=core.build(candidate,opts.output/'P1_compile.log',core.CANDIDATE_SHA)
            status.update({'P1':'PASS','binary_sha256':binary_sha})
            result=core.run_case(opts.case,pkg,candidate,historical,opts.output/'native_runs','attempt001',binary_sha,opts.timeout_seconds)
            status['case_result']=result
            for stage in ('P2','P3'):
                arr=[result.get('B',{}).get(stage),result.get('C',{}).get(stage)]
                status[stage]='PASS' if arr==['PASS','PASS'] else 'FAILED_OR_NOT_RUN'
            status['P4']=result.get('P4_csv','NOT_RUN')
        else:status['mode']='P0_AND_ARCHIVED_A_VERIFICATION_ONLY'
    except Exception as e:
        status['blocker']=type(e).__name__+': '+str(e)[:500]
    finally:
        status['science']='HOLD'
        summary=opts.output/'non_sensitive_status.json'
        # The full data / raw native logs stay in the job's ephemeral restricted workspace.
        summary.write_text(json.dumps(status,indent=2,sort_keys=True)+'\n')
        print(json.dumps(status,sort_keys=True))
    return 0 if status['P0']=='PASS' and (opts.mode!='run' or status['P4']=='PASS') else 3

if __name__=='__main__':raise SystemExit(main())