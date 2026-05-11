"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("workflow_runs", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("query", sa.Text(), nullable=False), sa.Column("mode", sa.String(32), nullable=False), sa.Column("provider", sa.String(64)), sa.Column("model", sa.String(128)), sa.Column("status", sa.String(32), nullable=False), sa.Column("final_answer", sa.Text()), sa.Column("request_id", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(128)), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("workflow_steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id"), nullable=False), sa.Column("node_name", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("retries", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime()), sa.Column("finished_at", sa.DateTime()), sa.Column("error", sa.JSON()))
    op.create_table("tool_calls", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id"), nullable=False), sa.Column("tool_name", sa.String(64), nullable=False), sa.Column("input_payload", sa.JSON(), nullable=False), sa.Column("output_payload", sa.JSON(), nullable=False), sa.Column("latency_ms", sa.Float(), nullable=False))
    op.create_table("llm_calls", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id"), nullable=False), sa.Column("provider", sa.String(64), nullable=False), sa.Column("model", sa.String(128), nullable=False), sa.Column("prompt_tokens", sa.Integer(), nullable=False), sa.Column("completion_tokens", sa.Integer(), nullable=False), sa.Column("latency_ms", sa.Float(), nullable=False), sa.Column("estimated_cost_usd", sa.Float(), nullable=False), sa.Column("success", sa.Boolean(), nullable=False))
    op.create_table("evidence_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id"), nullable=False), sa.Column("evidence_id", sa.String(32), nullable=False), sa.Column("url", sa.Text(), nullable=False), sa.Column("title", sa.Text(), nullable=False), sa.Column("snippet", sa.Text()), sa.Column("extracted_text", sa.Text()))
    op.create_table("citations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id"), nullable=False), sa.Column("section", sa.String(128), nullable=False), sa.Column("evidence_id", sa.String(32), nullable=False), sa.Column("url", sa.Text(), nullable=False))
    op.create_table("semantic_cache_entries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("key", sa.String(255), nullable=False), sa.Column("value", sa.JSON(), nullable=False))


def downgrade() -> None:
    for t in ["semantic_cache_entries", "citations", "evidence_items", "llm_calls", "tool_calls", "workflow_steps", "workflow_runs"]:
        op.drop_table(t)
