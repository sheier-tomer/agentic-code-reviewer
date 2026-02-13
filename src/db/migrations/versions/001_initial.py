"""Initial schema

Revision ID: 001_initial
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'repositories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('remote_url', sa.String(500)),
        sa.Column('default_branch', sa.String(100), default='main'),
        sa.Column('indexed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'code_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('repo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('repositories.id'), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('chunk_type', sa.String(50), nullable=False),
        sa.Column('symbol_name', sa.String(255)),
        sa.Column('start_line', sa.Integer, nullable=False),
        sa.Column('end_line', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('language', sa.String(50)),
        sa.Column('embedding', sa.Text),
        sa.Column('metadata', sa.JSON, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.execute("CREATE INDEX idx_code_chunks_file_path ON code_chunks (file_path)")
    op.execute("CREATE INDEX idx_code_chunks_symbol_name ON code_chunks (symbol_name)")

    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('repo_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('repositories.id')),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('task_description', sa.Text, nullable=False),
        sa.Column('status', sa.String(50), nullable=False, default='pending'),
        sa.Column('decision', sa.String(50)),
        sa.Column('quality_score', sa.Float),
        sa.Column('risk_score', sa.Float),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON, default={}),
    )

    op.create_index('idx_agent_runs_status', 'agent_runs', ['status'])
    op.create_index('idx_agent_runs_created_at', 'agent_runs', ['created_at'])

    op.create_table(
        'patches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id'), nullable=False),
        sa.Column('diff_content', sa.Text, nullable=False),
        sa.Column('files_affected', postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column('lines_added', sa.Integer),
        sa.Column('lines_removed', sa.Integer),
        sa.Column('applied_at', sa.DateTime(timezone=True)),
        sa.Column('sandbox_id', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'check_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id'), nullable=False),
        sa.Column('check_name', sa.String(100), nullable=False),
        sa.Column('passed', sa.Boolean, nullable=False),
        sa.Column('output', sa.Text),
        sa.Column('error_count', sa.Integer, default=0),
        sa.Column('warning_count', sa.Integer, default=0),
        sa.Column('details', sa.JSON, default=[]),
        sa.Column('duration_ms', sa.Integer),
        sa.Column('executed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('idx_check_results_run_id', 'check_results', ['run_id'])

    op.create_table(
        'tool_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id'), nullable=False),
        sa.Column('node_name', sa.String(100), nullable=False),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('input', sa.JSON),
        sa.Column('output', sa.JSON),
        sa.Column('success', sa.Boolean),
        sa.Column('error_message', sa.Text),
        sa.Column('duration_ms', sa.Integer),
        sa.Column('executed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id')),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_data', sa.JSON, nullable=False),
        sa.Column('actor', sa.String(100), default='system'),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index('idx_audit_log_run_id', 'audit_log', ['run_id'])
    op.create_index('idx_audit_log_event_type', 'audit_log', ['event_type'])
    op.create_index('idx_audit_log_created_at', 'audit_log', ['created_at'])


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('tool_executions')
    op.drop_table('check_results')
    op.drop_table('patches')
    op.drop_table('agent_runs')
    op.drop_table('code_chunks')
    op.drop_table('repositories')
    op.execute("DROP EXTENSION IF EXISTS vector")
