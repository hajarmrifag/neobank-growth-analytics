"""Create an ignored, private local password file without overwriting existing settings."""
import os
import secrets
from pathlib import Path

target = Path(__file__).resolve().parent.parent / '.env.api'
try:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env.api already exists; keeping its password.')
else:
    with os.fdopen(fd, 'w') as stream:
        stream.write('BANKING_DEMO_PASSWORD=' + secrets.token_hex(24) + '\n')
    print('Created private .env.api for the local API database.')
