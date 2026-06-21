import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class UserRole(enum.Enum):
    administrator = "administrator"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_type=False),
        nullable=False,
        default=UserRole.user,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
    blocked_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)

    @property
    def is_blocked(self) -> bool:
        return self.blocked_at is not None

    tickets_created = relationship(
        "Ticket", back_populates="creator", foreign_keys="Ticket.created_by"
    )
    assignments = relationship(
        "TicketAssignment", back_populates="user", foreign_keys="TicketAssignment.user_id"
    )
    progress_updates = relationship("ProgressUpdate", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")
