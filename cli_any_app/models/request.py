from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base

if TYPE_CHECKING:
    from cli_any_app.models.encrypted_payload import EncryptedPayload
    from cli_any_app.models.flow import Flow


class CapturedRequest(Base):
    __tablename__ = "requests"
    __table_args__ = (
        Index("ix_requests_flow_id", "flow_id"),
        Index("ix_requests_host", "host"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    method: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False, default="")
    redacted_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_headers: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_body_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_body_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_body_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_body_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_api: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    redaction_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="metadata_only",
    )

    flow: Mapped["Flow"] = relationship(back_populates="requests")
    encrypted_payload: Mapped["EncryptedPayload | None"] = relationship(
        back_populates="request", uselist=False, cascade="all, delete-orphan"
    )
