# ─────────────────────────────────────────────────────────────
# UniPredict AI — Configuration
# No database credentials needed — data is stored as CSV files
# in the  data/  folder next to this file.
# ─────────────────────────────────────────────────────────────

import os
import secrets

# Generate a secure secret key or load from environment
SECRET_KEY = os.environ.get('UNIPREDICT_SECRET_KEY') or secrets.token_urlsafe(32)

# Production settings
DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
HOST = os.environ.get('FLASK_HOST', '127.0.0.1')
PORT = int(os.environ.get('FLASK_PORT', 5000))

# Security settings
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))  # 1 hour
MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', 5))
LOGIN_LOCKOUT_TIME = int(os.environ.get('LOGIN_LOCKOUT_TIME', 900))  # 15 minutes
