import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_admin
from src.db.session import get_db
from src.schemas.schemas import UserCreate, UserListResponse, UserResponse, UserUpdate
from src.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _svc(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


@router.get("", response_model=UserListResponse, dependencies=[Depends(require_admin)])
async def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    svc: UserService = Depends(_svc),
):
    return await svc.list_users(offset=offset, limit=limit)


@router.post(
    "", response_model=UserResponse, status_code=201, dependencies=[Depends(require_admin)]
)
async def create_user(payload: UserCreate, svc: UserService = Depends(_svc)):
    return await svc.create_user(payload)


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def get_user(user_id: uuid.UUID, svc: UserService = Depends(_svc)):
    return await svc.get_user(user_id)


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def update_user(user_id: uuid.UUID, payload: UserUpdate, svc: UserService = Depends(_svc)):
    return await svc.update_user(user_id, payload)
