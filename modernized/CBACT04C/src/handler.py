"""Lambda entry point for CBACT04C (JCL INTCALC). S3 I/O only; logic is in cbact04c_logic."""
import os

import boto3

from cbact04c_logic import (
    ACCOUNT_RECORD_LEN, DISCGRP_RECORD_LEN, TCATBAL_RECORD_LEN, XREF_RECORD_LEN,
    CobolAbend, parse_records, run_intcalc,
)

PROGRAM = "CBACT04C"
DEFAULT_PARM = "2022071800"  # INTCALC.jcl STEP15 PARM
INPUTS = {
    # event key: (DD name, default S3 key, record length)
    "tcatbal_key": ("TCATBALF", f"in/{PROGRAM}/tcatbal.txt", TCATBAL_RECORD_LEN),
    "acctdata_key": ("ACCTFILE", f"in/{PROGRAM}/acctdata.txt", ACCOUNT_RECORD_LEN),
    "cardxref_key": ("XREFFILE", f"in/{PROGRAM}/cardxref.txt", XREF_RECORD_LEN),
    "discgrp_key": ("DISCGRP", f"in/{PROGRAM}/discgrp.txt", DISCGRP_RECORD_LEN),
}
OUTPUT_PREFIX = f"out/{PROGRAM}/"

_s3 = boto3.client("s3")


def handler(event, context):
    event = event or {}
    bucket = os.environ["DATA_BUCKET"]
    datasets = {}
    for event_key, (dd, default_key, length) in INPUTS.items():
        body = _s3.get_object(Bucket=bucket, Key=event.get(event_key, default_key))["Body"].read()
        datasets[dd] = parse_records(body, length)

    try:
        result = run_intcalc(
            datasets["TCATBALF"], datasets["ACCTFILE"], datasets["XREFFILE"], datasets["DISCGRP"],
            event.get("parm_date", DEFAULT_PARM),
        )
    except CobolAbend as abend:
        # Nothing is written on abend (TRANSACT is DISP=(NEW,CATLG,DELETE)).
        print("\n".join(abend.sysout))
        raise
    print("\n".join(result.sysout))

    outputs = {
        "TRANSACT.dat": b"".join(result.transactions),
        "ACCTFILE.dat": b"".join(result.accounts),
    }
    for name, data in outputs.items():
        _s3.put_object(Bucket=bucket, Key=OUTPUT_PREFIX + name, Body=data)

    return {
        "records_read": result.records_read,
        "transactions": len(result.transactions),
        "outputs": [OUTPUT_PREFIX + name for name in outputs],
    }
