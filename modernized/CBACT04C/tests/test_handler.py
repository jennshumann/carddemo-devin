import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from s3fake import FakeS3

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "app/data/ASCII"
NAMES = ("tcatbal.txt", "acctdata.txt", "cardxref.txt", "discgrp.txt")
BUCKET = "test-bucket"
CONTEXT = SimpleNamespace(aws_request_id="req-1")


@pytest.fixture
def handler_module(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    import handler
    return handler


def sample_inputs():
    return {(BUCKET, f"in/CBACT04C/{n}"): (SAMPLE / n).read_bytes() for n in NAMES}


def test_reads_in_prefix_and_commits_run_via_manifest(handler_module):
    s3 = FakeS3(sample_inputs())
    with mock.patch.object(handler_module, "_s3", s3):
        result = handler_module.handler({}, CONTEXT)
    assert [k for _, k in s3.gets] == [f"in/CBACT04C/{n}" for n in NAMES]
    run = "out/CBACT04C/runs/req-1/"
    # Manifest is written last: it is the commit point.
    assert [k for _, k in s3.puts] == [run + "TRANSACT.dat", run + "ACCTFILE.dat", "out/CBACT04C/LATEST.json"]
    manifest = json.loads(s3.objects[(BUCKET, "out/CBACT04C/LATEST.json")])
    assert manifest == {
        "program": "CBACT04C", "run_id": "req-1", "parm_date": "2022071800",
        "records_read": 50, "transactions": 50,
        "outputs": {"TRANSACT.dat": run + "TRANSACT.dat", "ACCTFILE.dat": run + "ACCTFILE.dat"},
    }
    assert result == {**manifest, "manifest": "out/CBACT04C/LATEST.json"}
    # Default PARM comes from INTCALC.jcl.
    assert s3.objects[(BUCKET, run + "TRANSACT.dat")][:16] == b"2022071800000001"


def test_failed_account_upload_leaves_manifest_unchanged(handler_module):
    previous = b'{"run_id": "previous"}'
    s3 = FakeS3({**sample_inputs(), (BUCKET, "out/CBACT04C/LATEST.json"): previous},
                fail_put_suffix="ACCTFILE.dat")
    with mock.patch.object(handler_module, "_s3", s3), pytest.raises(OSError):
        handler_module.handler({}, CONTEXT)
    assert s3.objects[(BUCKET, "out/CBACT04C/LATEST.json")] == previous


def test_event_overrides_input_keys_parm_and_run_id(handler_module):
    keys = {k: f"in/CBACT04C/alt/{n}" for k, n in
            zip(("tcatbal_key", "acctdata_key", "cardxref_key", "discgrp_key"), NAMES)}
    s3 = FakeS3({(BUCKET, keys[k]): (SAMPLE / n).read_bytes() for k, n in zip(keys, NAMES)})
    with mock.patch.object(handler_module, "_s3", s3):
        handler_module.handler({**keys, "parm_date": "2024010100", "run_id": "2024-01-01"}, CONTEXT)
    assert [k for _, k in s3.gets] == list(keys.values())
    assert s3.objects[(BUCKET, "out/CBACT04C/runs/2024-01-01/TRANSACT.dat")][:16] == b"2024010100000001"


@pytest.mark.parametrize("event", [{"acctdata_key": "in/CBACT01C/acctdata.txt"}, {"run_id": "../x"}])
def test_rejects_keys_outside_program_prefixes_and_bad_run_ids(handler_module, event):
    s3 = FakeS3(sample_inputs())
    with mock.patch.object(handler_module, "_s3", s3), pytest.raises(ValueError):
        handler_module.handler(event, CONTEXT)
    assert s3.puts == []


def test_previous_run_acctfile_can_be_fed_back(handler_module):
    """A previous run's ACCTFILE.dat (RECFM=F, read as fixed because of .dat) is a valid input."""
    golden = ROOT / "modernized/CBACT04C/golden/sample/ACCTFILE.dat"
    prior = "out/CBACT04C/runs/prev/ACCTFILE.dat"
    s3 = FakeS3({**sample_inputs(), (BUCKET, prior): golden.read_bytes()})
    with mock.patch.object(handler_module, "_s3", s3):
        handler_module.handler({"acctdata_key": prior}, CONTEXT)
    assert s3.objects[(BUCKET, "out/CBACT04C/runs/req-1/ACCTFILE.dat")] == golden.read_bytes()


def test_fixed_record_containing_lf_is_not_split(handler_module):
    """An explicit _format wins over the extension; LF bytes inside a fixed record are data."""
    golden = (ROOT / "modernized/CBACT04C/golden/sample/ACCTFILE.dat").read_bytes()
    first = bytearray(golden[:300])
    first[299] = 0x0A  # last FILLER byte
    data = bytes(first) + golden[300:]
    s3 = FakeS3({**sample_inputs(), (BUCKET, "in/CBACT04C/acct.bin"): data})
    with mock.patch.object(handler_module, "_s3", s3):
        result = handler_module.handler({"acctdata_key": "in/CBACT04C/acct.bin", "acctdata_format": "fixed"}, CONTEXT)
    out = s3.objects[(BUCKET, result["outputs"]["ACCTFILE.dat"])]
    assert len(out) == len(golden) and out[299:300] == b"\n"
