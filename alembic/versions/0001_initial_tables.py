"""create repositories and migration_jobs tables

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("default_branch", sa.String(100)),
        sa.Column("is_private", sa.Boolean()),
        sa.Column("stars", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "owner", "name"),
    )
    op.create_table(
        "migration_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("target_provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20)),
        sa.Column("attempts", sa.Integer()),
        sa.Column("target_url", sa.String(500)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    # only one pending/in_progress migration per repository
    op.create_index(
        "uq_one_active_migration_per_repo",
        "migration_jobs",
        ["repository_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'in_progress')"),
    )


def downgrade():
    op.drop_index("uq_one_active_migration_per_repo", table_name="migration_jobs")
    op.drop_table("migration_jobs")
    op.drop_table("repositories")
