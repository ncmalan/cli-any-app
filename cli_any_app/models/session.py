import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    app_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="stopped")
    proxy_port: Mapped[int] = mapped_column(Integer, default=8080)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    flows: Mapped[list["Flow"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    generated_cli: Mapped["GeneratedCLI | None"] = relationship(back_populates="session", uselist=False)
