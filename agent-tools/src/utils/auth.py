import time

import jwt

from src.config import Settings


def make_service_jwt(settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": "agent-tools",
        "iat": now,
        "exp": now + 60,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
