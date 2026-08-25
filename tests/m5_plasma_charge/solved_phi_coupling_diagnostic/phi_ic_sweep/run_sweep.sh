#!/usr/bin/env bash
set -u

if [ "$#" -ne 1 ]; then
  echo "usage: ./run_sweep.sh /path/to/working/qpx-opt"
  exit 2
fi

QPX="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$HERE/phi_ic_sweep.template.i"

if [ ! -x "$QPX" ]; then
  echo "qpx executable not found or not executable: $QPX"
  exit 2
fi

mkdir -p "$HERE/generated" "$HERE/logs" "$HERE/status"
rm -f "$HERE/generated"/phi_ic_*_out.csv
rm -f "$HERE/logs"/phi_ic_*.log
rm -f "$HERE/status"/phi_ic_*.status

run_case() {
  local stem="$1"
  local scale="$2"
  local input="$HERE/generated/${stem}.i"
  local log="$HERE/logs/${stem}.log"

  sed "s/__PHI_IC_SCALE__/${scale}/g" "$TEMPLATE" > "$input"

  echo
  echo "======================================================================"
  echo "$stem  (phi_ic_scale=$scale)"
  echo "======================================================================"

  (
    cd "$HERE/generated" || exit 2
    "$QPX" -i "${stem}.i" > "$log" 2>&1
  )
  local rc=$?
  echo "$rc" > "$HERE/status/${stem}.status"

  if [ "$rc" -eq 0 ]; then
    echo "SOLVE: PASS"
  else
    echo "SOLVE: FAIL ($rc)"
    tail -n 80 "$log"
  fi
}

run_case phi_ic_000 0.00
run_case phi_ic_025 0.25
run_case phi_ic_050 0.50
run_case phi_ic_075 0.75
run_case phi_ic_100 1.00

echo
echo "======================================================================"
echo "SWEEP ANALYSIS"
echo "======================================================================"
cd "$HERE" || exit 2
python3 analyze_sweep.py
