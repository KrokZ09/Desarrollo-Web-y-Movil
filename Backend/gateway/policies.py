import time
from collections import defaultdict, deque
from typing import Optional

import jwt


class AuthenticationPolicy:
    """Valida el token del usuario. Devuelve (id, rol) o None."""

    def __init__(self, key: str):
        self.key = key

    def verify(self, authorization: Optional[str]):
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        token = authorization[7:].strip()
        try:
            data = jwt.decode(
                token, self.key, algorithms=["HS256"], options={"require": ["exp", "sub", "role"]}
            )
        except jwt.PyJWTError:
            return None
        user_id, role = str(data["sub"]), data["role"]
        if not user_id.isdigit() or role not in ("cliente", "admin"):
            return None
        return user_id, role


class AuthorizationPolicy:
    """Decide por ruta qué roles pueden pasar. La propiedad de los recursos la valida cada servicio."""

    def check(self, route, role: str) -> bool:
        return role in route.roles


class RateLimitPolicy:
    """Límite de solicitudes por clave en una ventana de tiempo (en memoria)."""

    def __init__(self, window: int = 60):
        self.window = window
        self.hits = defaultdict(deque)

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True
