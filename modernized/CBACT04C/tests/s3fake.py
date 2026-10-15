import io


class FakeS3:
    """In-memory stand-in for the boto3 S3 client calls the handler makes."""

    def __init__(self, objects=None, fail_put_suffix=None):
        self.objects = dict(objects or {})
        self.gets, self.puts = [], []
        self.fail_put_suffix = fail_put_suffix

    def get_object(self, Bucket, Key):
        self.gets.append((Bucket, Key))
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def put_object(self, Bucket, Key, Body):
        if self.fail_put_suffix and Key.endswith(self.fail_put_suffix):
            raise OSError(f"simulated S3 failure writing {Key}")
        self.puts.append((Bucket, Key))
        self.objects[(Bucket, Key)] = Body
