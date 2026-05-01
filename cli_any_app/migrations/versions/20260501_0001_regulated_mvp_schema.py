"""regulated mvp schema

Revision ID: 20260501_0001
Revises:
Create Date: 2026-05-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260501_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("app_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("proxy_port", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("capture_token_hash", sa.String(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status in ('created','recording','stopped','generating','complete','error','validation_failed','needs_review','deleted')",
            name="ck_sessions_status",
        ),
    )
    op.create_table(
        "flows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("session_id", "order", name="uq_flows_session_order"),
    )
    op.create_index("ix_flows_session_id", "flows", ["session_id"])
    op.create_table(
        "requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("flow_id", sa.String(), sa.ForeignKey("flows.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("redacted_path", sa.Text(), nullable=False),
        sa.Column("request_headers", sa.Text(), nullable=False),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("request_body_size", sa.Integer(), nullable=False),
        sa.Column("request_body_hash", sa.String(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_headers", sa.Text(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_body_size", sa.Integer(), nullable=False),
        sa.Column("response_body_hash", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("is_api", sa.Boolean(), nullable=False),
        sa.Column("redaction_status", sa.String(), nullable=False),
    )
    op.create_index("ix_requests_flow_id", "requests", ["flow_id"])
    op.create_index("ix_requests_host", "requests", ["host"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_table(
        "domain_filters",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "domain", name="uq_domain_filters_session_domain"),
    )
    op.create_index("ix_domain_filters_session_id", "domain_filters", ["session_id"])
    op.create_table(
        "generated_clis",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("api_spec", sa.Text(), nullable=False),
        sa.Column("package_path", sa.String(), nullable=False),
        sa.Column("skill_md", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("redacted_input_hash", sa.String(), nullable=True),
        sa.Column("prompt_hash", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("response_id", sa.String(), nullable=True),
        sa.Column("file_hashes_json", sa.Text(), nullable=False),
        sa.Column("validation_report_json", sa.Text(), nullable=False),
        sa.Column("approval_status", sa.String(), nullable=False),
        sa.Column("package_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_generation_attempts_session_id", "generation_attempts", ["session_id"])
    op.create_table(
        "encrypted_payloads",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("request_id", sa.String(), sa.ForeignKey("requests.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("request_body_ciphertext", sa.Text(), nullable=True),
        sa.Column("response_body_ciphertext", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("encrypted_payloads")
    op.drop_index("ix_generation_attempts_session_id", table_name="generation_attempts")
    op.drop_table("generation_attempts")
    op.drop_table("generated_clis")
    op.drop_index("ix_domain_filters_session_id", table_name="domain_filters")
    op.drop_table("domain_filters")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_requests_host", table_name="requests")
    op.drop_index("ix_requests_flow_id", table_name="requests")
    op.drop_table("requests")
    op.drop_index("ix_flows_session_id", table_name="flows")
    op.drop_table("flows")
    op.drop_table("sessions")
