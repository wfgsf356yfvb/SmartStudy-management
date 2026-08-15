import os

USE_S3 = os.environ.get('USE_S3', '').lower() in ('1', 'true', 'yes')

if USE_S3:
    try:
        import boto3
        _s3 = boto3.client('s3')
    except Exception:
        _s3 = None
else:
    _s3 = None


def upload_file(bucket, key, filepath):
    if _s3:
        _s3.upload_file(filepath, bucket, key)
        return True
    raise RuntimeError('S3 not configured')


def download_file(bucket, key, filepath):
    if _s3:
        _s3.download_file(bucket, key, filepath)
        return True
    raise RuntimeError('S3 not configured')
