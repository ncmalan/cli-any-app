import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli_any_app.models.database import Base


class CapturedRequest(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    method: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    request_headers: Mapped[str] = mapped_column(Text, default="{}")
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[str] = mapped_column(Text, default="{}")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String, default="")
    is_api: Mapped[bool] = mapped_column(Boolean, default=True)

    flow: Mapped["Flow"] = relationship(back_populates="requests")
