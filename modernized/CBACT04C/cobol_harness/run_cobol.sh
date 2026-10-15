#!/usr/bin/env bash
# Compiles and runs the original CBACT04C (JCL INTCALC, STEP15) under
# GnuCOBOL and writes golden files. Never writes to app/.
# Usage: run_cobol.sh [input_dir] [output_dir] [parm]
#   input_dir holds tcatbal.txt, acctdata.txt, cardxref.txt, discgrp.txt
#   (default: app/data/ASCII). parm defaults to the JCL PARM.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
HARNESS="$REPO/modernized/CBACT04C/cobol_harness"
INPUT="$(realpath "${1:-$REPO/app/data/ASCII}")"
mkdir -p "${2:-$REPO/modernized/CBACT04C/golden/sample}"
GOLDEN="$(realpath "${2:-$REPO/modernized/CBACT04C/golden/sample}")"
PARM="${3:-2022071800}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cobc -x -fsign=EBCDIC -I "$REPO/app/cpy" -o "$WORK/intcalc" \
  "$HARNESS/INTCALC.cbl" "$REPO/app/cbl/CBACT04C.cbl" "$HARNESS/CEE3ABD.cbl"
cobc -x -o "$WORK/loaddata" "$HARNESS/LOADDATA.cbl"
cobc -x -o "$WORK/unldacct" "$HARNESS/UNLDACCT.cbl"

cd "$WORK"
DD_TCATIN="$INPUT/tcatbal.txt" DD_ACCTIN="$INPUT/acctdata.txt" \
DD_XREFIN="$INPUT/cardxref.txt" DD_DISCIN="$INPUT/discgrp.txt" \
DD_TCATBALF="$WORK/tcatbalf" DD_ACCTFILE="$WORK/acctfile" \
DD_XREFFILE="$WORK/xreffile" DD_DISCGRP="$WORK/discgrp" \
  ./loaddata

set +e
DD_TCATBALF="$WORK/tcatbalf" DD_ACCTFILE="$WORK/acctfile" \
DD_XREFFILE="$WORK/xreffile" DD_DISCGRP="$WORK/discgrp" \
DD_TRANSACT="$WORK/TRANSACT" \
  ./intcalc "$PARM" > "$WORK/SYSOUT" 2> "$WORK/STDERR"
RC=$?
set -e

DD_ACCTFILE="$WORK/acctfile" DD_ACCTOUT="$WORK/ACCTFILE" ./unldacct

rm -f "$GOLDEN"/*
echo "$RC" > "$GOLDEN/RC.txt"
cp "$WORK/SYSOUT" "$GOLDEN/SYSOUT.txt"
cp "$WORK/ACCTFILE" "$GOLDEN/ACCTFILE.dat"
# A z/OS abend deletes TRANSACT (DISP=(NEW,CATLG,DELETE)), so only keep it on RC 0.
if [ "$RC" -eq 0 ]; then cp "$WORK/TRANSACT" "$GOLDEN/TRANSACT.dat"; fi
echo "RC=$RC; golden files written to $GOLDEN"
