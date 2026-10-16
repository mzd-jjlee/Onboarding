"""Create local credentials once; never rotate keys on subsequent startup."""
from pathlib import Path
import os
import secrets

path = Path(__file__).resolve().parent.parent / '.env.superset'
if path.exists():
    print('Using existing .env.superset (credentials preserved).')
else:
    content = '\n'.join([
        'POSTGRES_USER=superset',
        'POSTGRES_DB=superset',
        'POSTGRES_PASSWORD=' + secrets.token_hex(24),
        'SUPERSET_SECRET_KEY=' + secrets.token_hex(48),
        'SUPERSET_ADMIN_USERNAME=admin',
        'SUPERSET_ADMIN_PASSWORD=' + secrets.token_urlsafe(16),
        '',
    ])
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    print('Created .env.superset with local credentials (mode 0600).')
