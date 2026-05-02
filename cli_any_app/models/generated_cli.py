from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cli_any_app.models.database import Base

if TYPE_CHECKING:
    from cli_any_app.models.session import Session


class GeneratedCLI(Base):
    __tablename__ = "generated_clis"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    api_spec: Mapped[str] = mapped_column(Text, default="{}")
    package_path: Mapped[str] = mapped_column(String, default="")
    skill_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    session: Mapped["Session"] = relationship(back_populates="generated_cli")
