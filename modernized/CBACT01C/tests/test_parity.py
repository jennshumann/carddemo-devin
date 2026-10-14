"""Byte-for-byte parity against outputs of the original COBOL (GnuCOBOL)."""
from pathlib import Path

import pytest

from cbact01c_logic import extract_accounts, from_gnucobol_varseq, parse_accounts

ROOT = Path(__file__).resolve().parents[3]
PROGRAM_DIR = ROOT / "modernized" / "CBACT01C"

CASES = {
    "sample": (ROOT / "app/data/ASCII/acctdata.txt", PROGRAM_DIR / "golden"),
    "edge": (PROGRAM_DIR / "tests/fixtures/edge_accounts.txt", PROGRAM_DIR / "golden/edge"),
}


@pytest.fixture(params=sorted(CASES), scope="module")
def case(request):
    input_path, golden = CASES[request.param]
    return extract_accounts(parse_accounts(input_path.read_bytes())), golden


def test_outfile_matches_golden(case):
    result, golden = case
    assert b"".join(result.out_records) == (golden / "OUTFILE.dat").read_bytes()


def test_arryfile_matches_golden(case):
    result, golden = case
    assert b"".join(result.array_records) == (golden / "ARRYFILE.dat").read_bytes()


def test_vbrcfile_records_match_golden(case):
    result, golden = case
    assert result.vb_records == from_gnucobol_varseq((golden / "VBRCFILE.dat").read_bytes())


def test_record_counts_match_golden_sysout():
    result, golden = CASES["sample"][0], CASES["sample"][1]
    sysout = (golden / "SYSOUT.txt").read_text()
    accounts = parse_accounts(result.read_bytes())
    assert sysout.count("ACCT-ID                 :") == len(accounts) == 50
