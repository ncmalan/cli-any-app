from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base

if TYPE_CHECKING:
    from cli_any_app.models.session import Session

from cli_any_app.models.request import CapturedRequest


class Flow(Base):
    __tablename__ = "flows"
    __table_args__ = (
        UniqueConstraint("session_id", "order", name="uq_flows_session_order"),
        Index("ix_flows_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped["Session"] = relationship(back_populates="flows")
    requests: Mapped[list["CapturedRequest"]] = relationship(
        back_populates="flow",
        cascade="all, delete-orphan",
        order_by=lambda: (CapturedRequest.timestamp, CapturedRequest.id),
    )
