# coding: utf-8
"""Session authentication (replaces HTTP basic auth).

- Passwords: scrypt (stdlib), format 'scrypt$<salt_hex>$<hash_hex>'.
- Sessions: signed token 'user_id.expires_ts.hmac' in an httponly cookie.
- Internal token: random per-boot secret used by the poll subprocess and the
  apscheduler system jobs to call our own HTTP endpoints (header X-Scrapydweb-Token).
"""
import hashlib
import hmac
import os
import time

SESSION_COOKIE = 'swsession'
SESSION_TTL = 14 * 24 * 3600  # 14 days
INTERNAL_TOKEN_HEADER = 'X-Scrapydweb-Token'

_SCRYPT = dict(n=2 ** 14, r=8, p=1)


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, **_SCRYPT)
    return 'scrypt$%s$%s' % (salt.hex(), digest.hex())


def verify_password(password, stored):
    try:
        algo, salt_hex, digest_hex = stored.split('$')
        if algo != 'scrypt':
            return False
        digest = hashlib.scrypt(password.encode('utf-8'),
                                salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except Exception:
        return False


def _sign(payload, secret):
    return hmac.new(secret.encode('utf-8'), payload.encode('utf-8'),
                    hashlib.sha256).hexdigest()


def create_session_token(user_id, secret, ttl=SESSION_TTL):
    payload = '%s.%s' % (user_id, int(time.time()) + ttl)
    return '%s.%s' % (payload, _sign(payload, secret))


def verify_session_token(token, secret):
    """Return user_id or None."""
    try:
        user_id, expires, sig = token.split('.')
        payload = '%s.%s' % (user_id, expires)
        if not hmac.compare_digest(sig, _sign(payload, secret)):
            return None
        if int(expires) < time.time():
            return None
        return int(user_id)
    except Exception:
        return None
