from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.auth_adapter import KeycloakValidator, UnauthorizedError, UserClaims

_bearer = HTTPBearer(auto_error=False)
_validator = KeycloakValidator()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserClaims:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await _validator.verify(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(role: str) -> Depends:
    async def dependency(claims: UserClaims = Depends(get_current_user)) -> UserClaims:
        if role == "administrator" and not claims.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return claims

    return Depends(dependency)


async def _service_account_or_admin(claims: UserClaims = Depends(get_current_user)) -> UserClaims:
    if not claims.is_admin and not claims.is_service_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return claims


require_service_account_or_admin = Depends(_service_account_or_admin)
