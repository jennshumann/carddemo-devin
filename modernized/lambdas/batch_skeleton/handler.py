import json
import os


def handler(event, context):
    return {
        "status": "ok",
        "bucket": os.environ.get("DATA_BUCKET"),
        "dbSecretArn": os.environ.get("DB_SECRET_ARN"),
        "event": json.loads(json.dumps(event, default=str)),
    }
