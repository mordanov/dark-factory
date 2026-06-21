from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.ticket import UserSummary

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserSummary])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[User]:
    result = await db.execute(select(User).order_by(User.email))
    return list(result.scalars().all())
