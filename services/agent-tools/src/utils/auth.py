from src.core.auth_adapter import KeycloakValidator


async def verify_token(token: str) -> dict:
    adapter = KeycloakValidator()
    return await adapter.verify(token)
