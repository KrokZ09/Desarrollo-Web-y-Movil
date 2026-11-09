import hashlib
import hmac
import os
import time

import jwt

from secrets_provider import get_secret

# scrypt: hash adaptativo (lento a propósito) con sal aleatoria por usuario
N, R, P = 2**15, 8, 1
MAXMEM = 128 * 1024 * 1024
TOKEN_SECONDS = 1800  # 30 minutos

JWT_KEY = get_secret("JWT_SIGNING")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=N, r=R, p=P, maxmem=MAXMEM, dklen=32
    )
    # Se guardan los parámetros: si se endurecen después, los hashes viejos siguen validando
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        calc = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=MAXMEM,
            dklen=32,
        )
    except Exception:
        return False
    return hmac.compare_digest(calc, bytes.fromhex(digest))


def create_token(user_id: int, role: str) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + TOKEN_SECONDS}
    return jwt.encode(payload, JWT_KEY, algorithm="HS256")
