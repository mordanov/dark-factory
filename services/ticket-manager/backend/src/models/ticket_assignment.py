from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class TicketAssignment(Base):
    __tablename__ = "ticket_assignments"
    __table_args__ = (
        UniqueConstraint("ticket_id", "user_id", name="uq_ticket_assignments_ticket_user"),
        Index("idx_ticket_assignments_ticket_id", "ticket_id"),
        Index("idx_ticket_assignments_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_by: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    ticket = relationship("Ticket", back_populates="assignments")
