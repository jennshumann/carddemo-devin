from pathlib import Path
from unittest import mock

import pytest

from s3fake import FakeS3

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "app/data/ASCII"
NAMES = ("tcatbal.txt", "acctdata.txt", "cardxref.txt", "discgrp.txt")


@pytest.fixture
def handler_module(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    import handler
    return handler


def test_reads_in_prefix_and_writes_out_prefix(handler_module):
    s3 = FakeS3({("test-bucket", f"in/CBACT04C/{n}"): (SAMPLE / n).read_bytes() for n in NAMES})
    with mock.patch.object(handler_module, "_s3", s3):
        result = handler_module.handler({}, None)
    assert [k for _, k in s3.gets] == [f"in/CBACT04C/{n}" for n in NAMES]
    assert [k for _, k in s3.puts] == ["out/CBACT04C/TRANSACT.dat", "out/CBACT04C/ACCTFILE.dat"]
    assert result == {
        "records_read": 50, "transactions": 50,
        "outputs": ["out/CBACT04C/TRANSACT.dat", "out/CBACT04C/ACCTFILE.dat"],
    }
    # Default PARM comes from INTCALC.jcl.
    assert s3.objects[("test-bucket", "out/CBACT04C/TRANSACT.dat")][:16] == b"2022071800000001"


def test_event_overrides_input_keys_and_parm(handler_module):
    keys = {"tcatbal_key": "x/t", "acctdata_key": "x/a", "cardxref_key": "x/c", "discgrp_key": "x/d"}
    s3 = FakeS3({("test-bucket", keys[k]): (SAMPLE / n).read_bytes() for k, n in zip(keys, NAMES)})
    with mock.patch.object(handler_module, "_s3", s3):
        handler_module.handler({**keys, "parm_date": "2024010100"}, None)
    assert [k for _, k in s3.gets] == list(keys.values())
    assert s3.objects[("test-bucket", "out/CBACT04C/TRANSACT.dat")][:16] == b"2024010100000001"


def test_accepts_fixed_length_acctfile_from_a_previous_run(handler_module):
    """ACCTFILE.dat output (RECFM=F, no newlines) can be fed back in."""
    golden = ROOT / "modernized/CBACT04C/golden/sample/ACCTFILE.dat"
    objects = {("test-bucket", f"in/CBACT04C/{n}"): (SAMPLE / n).read_bytes() for n in NAMES}
    objects[("test-bucket", "in/CBACT04C/acctdata.txt")] = golden.read_bytes()
    s3 = FakeS3(objects)
    with mock.patch.object(handler_module, "_s3", s3):
        handler_module.handler({}, None)
    assert s3.objects[("test-bucket", "out/CBACT04C/ACCTFILE.dat")] == golden.read_bytes()
