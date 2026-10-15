"""Lambda entry point for CBACT04C (JCL INTCALC). S3 I/O only; logic is in cbact04c_logic."""
import json
import os
import re
import uuid

import boto3

from cbact04c_logic import (
    ACCOUNT_RECORD_LEN, DISCGRP_RECORD_LEN, TCATBAL_RECORD_LEN, XREF_RECORD_LEN,
    CobolAbend, parse_records, run_intcalc,
)

PROGRAM = "CBACT04C"
DEFAULT_PARM = "2022071800"  # INTCALC.jcl STEP15 PARM
INPUT_PREFIX = f"in/{PROGRAM}/"
OUTPUT_PREFIX = f"out/{PROGRAM}/"
MANIFEST_KEY = OUTPUT_PREFIX + "LATEST.json"
INPUTS = {
    # event key: (DD name, default S3 key, record length)
    "tcatbal_key": ("TCATBALF", INPUT_PREFIX + "tcatbal.txt", TCATBAL_RECORD_LEN),
    "acctdata_key": ("ACCTFILE", INPUT_PREFIX + "acctdata.txt", ACCOUNT_RECORD_LEN),
    "cardxref_key": ("XREFFILE", INPUT_PREFIX + "cardxref.txt", XREF_RECORD_LEN),
    "discgrp_key": ("DISCGRP", INPUT_PREFIX + "discgrp.txt", DISCGRP_RECORD_LEN),
}
RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

_s3 = boto3.client("s3")


def _input_key(event: dict, event_key: str, default_key: str) -> str:
    key = event.get(event_key, default_key)
    # IAM only grants reads on these prefixes; fail with a clear message instead of AccessDenied.
    if not key.startswith((INPUT_PREFIX, OUTPUT_PREFIX)):
        raise ValueError(f"{event_key} must be under {INPUT_PREFIX} or {OUTPUT_PREFIX}: {key!r}")
    return key


def _input_format(event: dict, event_key: str, key: str) -> str:
    """'fixed' for RECFM=F .dat files (e.g. a previous run's ACCTFILE.dat), else 'line'."""
    return event.get(event_key.replace("_key", "_format")) or ("fixed" if key.endswith(".dat") else "line")


def handler(event, context):
    event = event or {}
    bucket = os.environ["DATA_BUCKET"]
    run_id = event.get("run_id") or getattr(context, "aws_request_id", None) or uuid.uuid4().hex
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"invalid run_id {run_id!r}")

    datasets = {}
    for event_key, (dd, default_key, length) in INPUTS.items():
        key = _input_key(event, event_key, default_key)
        body = _s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        datasets[dd] = parse_records(body, length, _input_format(event, event_key, key))

    parm = event.get("parm_date", DEFAULT_PARM)
    try:
        result = run_intcalc(
            datasets["TCATBALF"], datasets["ACCTFILE"], datasets["XREFFILE"], datasets["DISCGRP"], parm,
        )
    except CobolAbend as abend:
        # Nothing is written on abend (TRANSACT is DISP=(NEW,CATLG,DELETE)).
        print("\n".join(abend.sysout))
        raise
    print("\n".join(result.sysout))

    # Both files go under a per-run prefix; LATEST.json is written last and is the
    # single commit point, so a failed upload never pairs new transactions with old accounts.
    run_prefix = f"{OUTPUT_PREFIX}runs/{run_id}/"
    outputs = {
        "TRANSACT.dat": b"".join(result.transactions),
        "ACCTFILE.dat": b"".join(result.accounts),
    }
    for name, data in outputs.items():
        _s3.put_object(Bucket=bucket, Key=run_prefix + name, Body=data)
    manifest = {
        "program": PROGRAM,
        "run_id": run_id,
        "parm_date": parm,
        "records_read": result.records_read,
        "transactions": len(result.transactions),
        "outputs": {name: run_prefix + name for name in outputs},
    }
    _s3.put_object(Bucket=bucket, Key=MANIFEST_KEY, Body=json.dumps(manifest, indent=2).encode())
    return {**manifest, "manifest": MANIFEST_KEY}
