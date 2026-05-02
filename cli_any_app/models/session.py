from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base

if TYPE_CHECKING:
    from cli_any_app.models.domain_filter import DomainFilter
    from cli_any_app.models.flow import Flow
    from cli_any_app.models.generated_cli import GeneratedCLI
    from cli_any_app.models.generation_attempt import GenerationAttempt


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status in ('created','recording','stopped','generating','complete','error','validation_failed','needs_review','deleted')",
            name="ck_sessions_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    app_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="created")
    proxy_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8080)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    capture_token_hash: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    captured_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    flows: Mapped[list["Flow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    generated_cli: Mapped["GeneratedCLI | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    domain_filters: Mapped[list["DomainFilter"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    generation_attempts: Mapped[list["GenerationAttempt"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
