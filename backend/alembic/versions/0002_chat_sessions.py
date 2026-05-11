"""chat sessions

Revision ID: 0002_chat_sessions
Revises: 0001_init
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_chat_sessions"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.add_column("workflow_runs", sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_workflow_runs_session_id", "workflow_runs", "chat_sessions", ["session_id"], ["id"])
    op.create_index("ix_workflow_runs_session_id", "workflow_runs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_session_id", table_name="workflow_runs")
    op.drop_constraint("fk_workflow_runs_session_id", "workflow_runs", type_="foreignkey")
    op.drop_column("workflow_runs", "session_id")
    op.drop_table("chat_sessions")
