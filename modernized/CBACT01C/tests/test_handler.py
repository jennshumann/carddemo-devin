import io
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def handler_module(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    import handler
    return handler


def test_handler_reads_in_prefix_and_writes_out_prefix(handler_module):
    s3 = mock.Mock()
    s3.get_object.return_value = {
        "Body": io.BytesIO((ROOT / "app/data/ASCII/acctdata.txt").read_bytes())
    }
    with mock.patch.object(handler_module, "_s3", s3):
        result = handler_module.handler({}, None)

    s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="in/CBACT01C/acctdata.txt")
    keys = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
    assert keys == [
        "out/CBACT01C/OUTFILE.dat", "out/CBACT01C/ARRYFILE.dat", "out/CBACT01C/VBRCFILE.dat",
    ]
    golden = ROOT / "modernized/CBACT01C/golden"
    bodies = {c.kwargs["Key"]: c.kwargs["Body"] for c in s3.put_object.call_args_list}
    assert bodies["out/CBACT01C/OUTFILE.dat"] == (golden / "OUTFILE.dat").read_bytes()
    assert result["accounts"] == 50
