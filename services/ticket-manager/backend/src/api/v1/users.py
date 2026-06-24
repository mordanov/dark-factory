from fastapi import APIRouter, Depends

from src.core.auth_adapter import UserClaims
from src.core.security import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list)
async def list_users(
    _: UserClaims = Depends(get_current_user),
) -> list:
    return []
