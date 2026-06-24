from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(8), unique=True, nullable=True, index=True)
    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("project_groups.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    group: Mapped["ProjectGroup"] = relationship(
        "ProjectGroup", back_populates="projects", lazy="joined"
    )
    tickets = relationship("Ticket", back_populates="project")
