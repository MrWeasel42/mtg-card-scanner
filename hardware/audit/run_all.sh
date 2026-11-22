#!/bin/bash
# The whole audit, start to finish (re-run after ANY design change).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../cad"
python3 sorter.py > $HERE/out_export.log 2>&1
python3 wiring.py > /dev/null 2>&1 || true
cd "$HERE"
python3 export_placed.py > /dev/null
python3 pairs.py > out_pairs.log 2>&1
python3 joints.py > out_joints.log 2>&1
python3 wires.py > out_wires.log 2>&1
python3 motion.py > out_motion.log 2>&1
python3 sim.py > out_sim.log 2>&1
python3 printability.py > out_print.log 2>&1
python3 tips_check.py > out_tips.log 2>&1
python3 test_sections.py > out_sections.log 2>&1
python3 insert_walls.py > out_inserts.log 2>&1
cd "$HERE/../cad" && python3 fitcheck.py $HERE/fit.json > $HERE/out_fit.log 2>&1
cd "$HERE"
echo "pairs:  $(grep -v 'shaft_\|coupler\|v_\|psu_body' out_pairs.log | grep -c '^(' ) unexpected overlaps"
echo "joints: $(tail -1 out_joints.log)"
echo "wires:  $(grep -c '^OK' out_wires.log) ok, $(grep -c '^HIT' out_wires.log) hit"
echo "motion: $(grep -c '^PASS' out_motion.log) pass, $(grep -c '^FAIL' out_motion.log) fail"
echo "sim:    $(grep -c 'collisions: none' out_sim.log) / 3 cards clean"
echo "insert walls: $(tail -1 out_inserts.log)"
echo "fit:    $(tail -1 out_fit.log)"
