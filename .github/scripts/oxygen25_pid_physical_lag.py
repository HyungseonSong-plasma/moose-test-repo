#!/usr/bin/env python3
"""Physical-time PID lag diagnostic for verified 1000 W native MOOSE plasma.csv.

An observational cross-correlation, not a PID/Maxwell causality test, and
not evidence that Stage6 dtmax=100us is numerically safe.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from pathlib import Path

RF = 'P_rf_raw_W_t6'
DRIVE = 'rf_drive_scale_t6'
TARGET = 1000.0
CLAMP = 3.0
END_S = 0.001
LATE_S = 0.0005


def load(path: Path) -> list[tuple[float, float, float]]:
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        required = {'time', RF, DRIVE}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('native RF/drive monitor columns absent')
        rows = [(float(r['time']), float(r[RF]), float(r[DRIVE])) for r in reader]
    if len(rows) < 100 or any(not all(map(math.isfinite, r)) for r in rows):
        raise ValueError('insufficient or nonfinite native history')
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('native time not strictly increasing')
    if not math.isclose(rows[0][0], 0, abs_tol=1e-15) or not math.isclose(rows[-1][0], END_S, abs_tol=1e-15):
        raise ValueError('native CSV must cover 0..1ms')
    if any(p <= 0 or not 0 < drive <= CLAMP + 1e-8 for _, p, drive in rows):
        raise ValueError('invalid native RF or PID drive')
    return rows


def interpolate(t: list[float], y: list[float], x: float) -> float:
    if x < t[0] or x > t[-1]:
        raise ValueError('interpolation outside native time range')
    j = bisect.bisect_left(t, x)
    if j == 0:
        return y[0]
    if j == len(t):
        return y[-1]
    if x == t[j]:
        return y[j]
    a = (x-t[j-1])/(t[j]-t[j-1])
    return (1-a)*y[j-1]+a*y[j]


def weighted_corr(x: list[float], y: list[float], weights: list[float]) -> float | None:
    if len(x) < 12 or sum(weights) <= 0:
        return None
    total = sum(weights)
    mx = sum(a*w for a,w in zip(x,weights))/total
    my = sum(b*w for b,w in zip(y,weights))/total
    c = sum(w*(a-mx)*(b-my) for a,b,w in zip(x,y,weights))
    vx = sum(w*(a-mx)**2 for a,w in zip(x,weights))
    vy = sum(w*(b-my)**2 for b,w in zip(y,weights))
    return c/math.sqrt(vx*vy) if vx > 1e-20 and vy > 1e-20 else None


def diagnose(rows: list[tuple[float,float,float]], lag_us: list[float]) -> dict:
    t = [r[0] for r in rows]
    power = [r[1] for r in rows]
    drive = [r[2] for r in rows]
    results = []
    for lag in lag_us:
        if lag < 0:
            raise ValueError('lag must be nonnegative')
        errors, changes, weights = [], [], []
        delay = lag*1e-6
        for i in range(1,len(t)):
            mid = (t[i]+t[i-1])/2
            if mid < LATE_S or mid > END_S:
                continue
            if drive[i] >= CLAMP-1e-8 or drive[i-1] >= CLAMP-1e-8:
                continue
            observed_at = mid-delay
            if observed_at < LATE_S or observed_at < t[0]:
                continue
            dt = t[i]-t[i-1]
            errors.append(interpolate(t,power,observed_at)-TARGET)
            changes.append((drive[i]-drive[i-1])/dt)
            weights.append(dt)
        results.append({'lag_us':lag,'intervals':len(errors),
                        'covered_time_us':sum(weights)*1e6,
                        'correlation':weighted_corr(errors,changes,weights)})
    valid = [x for x in results if x['correlation'] is not None]
    return {
        'scientific_decision':'HOLD_STAGE6',
        'method':'dt-weighted correlation between RF error at physical time t-lag and PID drive rate over unsaturated interval centered at t',
        'lag_grid_us':lag_us,
        'results':results,
        'strongest_negative_correlation':min(valid,key=lambda x:x['correlation']) if valid else None,
        'limitations':'Sampled postprocessor monitors, interpolation and controller update ordering limit causal interpretation. One timestep refinement cannot validate 100us Stage6 dtmax.'
    }


def self_test() -> None:
    for dt in (5e-6, 10e-6):
        rows = []
        drive = 2.0
        count = round(END_S/dt)
        for i in range(count+1):
            t = i*dt
            if i:
                mid = (i-0.5)*dt
                delayed_error = 100*math.sin(2*math.pi*(mid-10e-6)/80e-6)
                drive -= 0.0005*delayed_error
            rows.append((t,1000+100*math.sin(2*math.pi*t/80e-6),drive))
        assert min(r[2] for r in rows)>0 and max(r[2] for r in rows)<CLAMP
        report = diagnose(rows,[0.,5.,10.,15.,20.])
        best = report['strongest_negative_correlation']
        assert best is not None and best['lag_us'] == 10.0, best
        assert best['correlation'] < -0.95, best
        assert report['scientific_decision']=='HOLD_STAGE6'
    print('OXYGEN25_PID_PHYSICAL_LAG_SELFTEST_PASS')


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',type=Path)
    parser.add_argument('--output-json',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.csv or not args.output_json:
        parser.error('require --csv and --output-json')
    report=diagnose(load(args.csv),[float(v) for v in range(0,41,5)])
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('OXYGEN25_PID_PHYSICAL_LAG',json.dumps(report['strongest_negative_correlation']),flush=True)


if __name__=='__main__':
    main()
