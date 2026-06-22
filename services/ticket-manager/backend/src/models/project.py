from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True, index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])
    tickets = relationship("Ticket", back_populates="project")
