from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base

if TYPE_CHECKING:
    from cli_any_app.models.request import CapturedRequest


class EncryptedPayload(Base):
    __tablename__ = "encrypted_payloads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), nullable=False, unique=True)
    request_body_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_body_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    request: Mapped["CapturedRequest"] = relationship(back_populates="encrypted_payload")
