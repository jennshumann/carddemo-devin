"""Lambda entry point for CBACT01C. S3 I/O only; logic is in cbact01c_logic."""
import os

import boto3

from cbact01c_logic import extract_accounts, parse_accounts, to_rdw

PROGRAM = "CBACT01C"
DEFAULT_INPUT_KEY = f"in/{PROGRAM}/acctdata.txt"
OUTPUT_PREFIX = f"out/{PROGRAM}/"

_s3 = boto3.client("s3")


def handler(event, context):
    bucket = os.environ["DATA_BUCKET"]
    input_key = (event or {}).get("input_key", DEFAULT_INPUT_KEY)
    body = _s3.get_object(Bucket=bucket, Key=input_key)["Body"].read()

    accounts = parse_accounts(body)
    result = extract_accounts(accounts)

    outputs = {
        "OUTFILE.dat": b"".join(result.out_records),
        "ARRYFILE.dat": b"".join(result.array_records),
        "VBRCFILE.dat": to_rdw(result.vb_records),
    }
    for name, data in outputs.items():
        _s3.put_object(Bucket=bucket, Key=OUTPUT_PREFIX + name, Body=data)

    print(f"START OF EXECUTION OF PROGRAM {PROGRAM}")
    print(f"ACCOUNTS PROCESSED: {len(accounts)}")
    print(f"END OF EXECUTION OF PROGRAM {PROGRAM}")
    return {
        "accounts": len(accounts),
        "outputs": [OUTPUT_PREFIX + name for name in outputs],
    }
