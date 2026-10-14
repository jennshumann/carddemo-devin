#!/usr/bin/env bash
# Compiles and runs the original CBACT01C under GnuCOBOL against
# an ASCII account extract and writes golden files. Never writes to app/.
# Usage: run_cobol.sh [input.txt] [output_dir]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
HARNESS="$REPO/modernized/CBACT01C/cobol_harness"
INPUT="$(realpath "${1:-$REPO/app/data/ASCII/acctdata.txt}")"
mkdir -p "${2:-$REPO/modernized/CBACT01C/golden}"
GOLDEN="$(realpath "${2:-$REPO/modernized/CBACT01C/golden}")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cobc -x -fsign=EBCDIC -I "$REPO/app/cpy" -o "$WORK/cbact01c" \
  "$REPO/app/cbl/CBACT01C.cbl" "$HARNESS/COBDATFT.cbl" "$HARNESS/CEE3ABD.cbl"
cobc -x -o "$WORK/loadacct" "$HARNESS/LOADACCT.cbl"

cd "$WORK"
DD_ACCTIN="$INPUT" DD_ACCTFILE="$WORK/acctfile" ./loadacct
DD_ACCTFILE="$WORK/acctfile" DD_OUTFILE="$WORK/OUTFILE" \
DD_ARRYFILE="$WORK/ARRYFILE" DD_VBRCFILE="$WORK/VBRCFILE" \
  ./cbact01c > "$WORK/SYSOUT"

cp "$WORK/OUTFILE" "$GOLDEN/OUTFILE.dat"
cp "$WORK/ARRYFILE" "$GOLDEN/ARRYFILE.dat"
cp "$WORK/VBRCFILE" "$GOLDEN/VBRCFILE.dat"
cp "$WORK/SYSOUT" "$GOLDEN/SYSOUT.txt"
echo "golden files written to $GOLDEN"
