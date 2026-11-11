"""Create local MinIO credentials once; never rotate keys on subsequent startup."""
from pathlib import Path
import os
import secrets

path = Path(__file__).resolve().parent.parent / '.env.minio'
if path.exists():
    print('Using existing .env.minio (credentials preserved).')
else:
    password = secrets.token_hex(24)
    content = '\n'.join([
        # MinIO server admin account (web console login).
        'MINIO_ROOT_USER=lakehouse',
        'MINIO_ROOT_PASSWORD=' + password,
        # Same keys for S3 clients (HMS/SeaTunnel s3a, Trino) via the AWS default credential chain.
        'AWS_ACCESS_KEY_ID=lakehouse',
        'AWS_SECRET_ACCESS_KEY=' + password,
        'AWS_REGION=us-east-1',
        '',
    ])
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    print('Created .env.minio with local credentials (mode 0600).')
