"""Parity of the Lambda against golden outputs of the original COBOL (GnuCOBOL).

TRANSACT is compared byte for byte with only TRAN-ORIG-TS and TRAN-PROC-TS
masked. ACCTFILE and SYSOUT are compared exactly.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from cbact04c_logic import TRAN_ORIG_TS, TRAN_PROC_TS, TRAN_RECORD_LEN, CobolAbend
from s3fake import FakeS3

ROOT = Path(__file__).resolve().parents[3]
PROGRAM_DIR = ROOT / "modernized" / "CBACT04C"
FIXTURES = PROGRAM_DIR / "tests" / "fixtures"
GOLDEN = PROGRAM_DIR / "golden"
HARNESS = PROGRAM_DIR / "cobol_harness" / "run_cobol.sh"
PARM = "2022071800"
BUCKET = "test-bucket"

INPUT_DIRS = {
    "sample": ROOT / "app" / "data" / "ASCII",
    "edge": FIXTURES / "edge",
    "empty": FIXTURES / "empty",
    "abend_acct": FIXTURES / "abend_acct",
    "abend_xref": FIXTURES / "abend_xref",
    "abend_discgrp": FIXTURES / "abend_discgrp",
}
SUCCESS_CASES = ["sample", "edge", "empty"]
ABEND_CASES = ["abend_acct", "abend_xref", "abend_discgrp"]
TS_PATTERN = re.compile(rb"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d{2}0000")


def mask_timestamps(data: bytes) -> bytes:
    assert len(data) % TRAN_RECORD_LEN == 0
    out = bytearray(data)
    for start in range(0, len(data), TRAN_RECORD_LEN):
        for ts in (TRAN_ORIG_TS, TRAN_PROC_TS):
            field = slice(start + ts.start, start + ts.stop)
            assert TS_PATTERN.fullmatch(out[field]), bytes(out[field])
            out[field] = b"#" * (ts.stop - ts.start)
    return bytes(out)


def read_output(s3, name):
    manifest = json.loads(s3.objects[(BUCKET, "out/CBACT04C/LATEST.json")])
    return s3.objects[(BUCKET, manifest["outputs"][name])]


def run_lambda(handler_module, case):
    src = INPUT_DIRS[case]
    s3 = FakeS3({
        (BUCKET, f"in/CBACT04C/{name}"): (src / name).read_bytes()
        for name in ("tcatbal.txt", "acctdata.txt", "cardxref.txt", "discgrp.txt")
    })
    with mock.patch.object(handler_module, "_s3", s3):
        try:
            handler_module.handler({"parm_date": PARM}, None)
        except CobolAbend as abend:
            return s3, abend
    return s3, None


@pytest.fixture
def handler_module(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    import handler
    return handler


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_transact_matches_golden_except_timestamps(handler_module, case):
    s3, abend = run_lambda(handler_module, case)
    assert abend is None
    actual = read_output(s3, "TRANSACT.dat")
    golden = (GOLDEN / case / "TRANSACT.dat").read_bytes()
    assert len(actual) == len(golden)
    assert mask_timestamps(actual) == mask_timestamps(golden)


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_acctfile_matches_golden(handler_module, case):
    s3, _ = run_lambda(handler_module, case)
    actual = read_output(s3, "ACCTFILE.dat")
    assert actual == (GOLDEN / case / "ACCTFILE.dat").read_bytes()


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_sysout_matches_golden(handler_module, case, capsys):
    run_lambda(handler_module, case)
    assert capsys.readouterr().out == (GOLDEN / case / "SYSOUT.txt").read_text()
    assert (GOLDEN / case / "RC.txt").read_text().strip() == "0"


@pytest.mark.parametrize("case", ABEND_CASES)
def test_abend_matches_golden(handler_module, case, capsys):
    s3, abend = run_lambda(handler_module, case)
    assert abend is not None and abend.code == 999
    assert s3.puts == []
    assert capsys.readouterr().out == (GOLDEN / case / "SYSOUT.txt").read_text()
    # CEE3ABD stand-in sets RETURN-CODE 999; the shell sees it modulo 256.
    assert int((GOLDEN / case / "RC.txt").read_text()) == 999 % 256
    assert not (GOLDEN / case / "TRANSACT.dat").exists()
    assert s3.puts == []


def test_edge_case_covers_the_interesting_paths():
    """Guard against the edge fixture silently losing coverage."""
    sysout = (GOLDEN / "edge" / "SYSOUT.txt").read_text()
    assert "TRY WITH DEFAULT GROUP CODE" in sysout
    transact = (GOLDEN / "edge" / "TRANSACT.dat").read_bytes()
    amounts = {transact[i + 132:i + 143] for i in range(0, len(transact), TRAN_RECORD_LEN)}
    assert b"0000000012N" in amounts      # negative interest (-1.25)
    assert b"3333249999A" in amounts      # high-order truncation on overflow
    assert b"0000000000{" in amounts      # truncated to zero, still written


@pytest.mark.skipif(shutil.which("cobc") is None, reason="GnuCOBOL not installed")
@pytest.mark.parametrize("case", SUCCESS_CASES + ABEND_CASES)
def test_golden_files_are_reproducible(case, tmp_path):
    """Re-run the original COBOL and check the committed golden files still match."""
    subprocess.run([str(HARNESS), str(INPUT_DIRS[case]), str(tmp_path), PARM],
                   check=True, capture_output=True)
    committed = GOLDEN / case
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(p.name for p in committed.iterdir())
    for name in ("ACCTFILE.dat", "SYSOUT.txt", "RC.txt"):
        assert (tmp_path / name).read_bytes() == (committed / name).read_bytes(), name
    if (committed / "TRANSACT.dat").exists():
        assert mask_timestamps((tmp_path / "TRANSACT.dat").read_bytes()) == \
            mask_timestamps((committed / "TRANSACT.dat").read_bytes())
