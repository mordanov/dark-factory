from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import UserClaims
from src.core.database import get_db
from src.core.security import get_current_user
from src.models.tag import Tag
from src.schemas.ticket import TagResponse

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("", response_model=list[TagResponse])
async def search_tags(
    q: str = Query(min_length=1, max_length=50),
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(get_current_user),
) -> list[Tag]:
    result = await db.execute(
        select(Tag).where(Tag.name.ilike(f"{q}%")).order_by(Tag.name).limit(10)
    )
    return list(result.scalars().all())
