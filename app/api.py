"""Token-authenticated JSON API for automation (Home Assistant, panels)."""
import hashlib
import secrets


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_token():
    return 'cl_' + secrets.token_urlsafe(32)
