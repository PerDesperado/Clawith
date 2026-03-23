"""Add org_role column to user_agent_bindings table.

Revision ID: add_org_role_to_bindings
Revises: df3da9cf3b27
"""
from alembic import op
import sqlalchemy as sa

revision = "add_org_role_to_bindings"
down_revision = "df3da9cf3b27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add org_role column: "leader" (组长) or "member" (组员)
    op.execute("""
        ALTER TABLE user_agent_bindings 
        ADD COLUMN IF NOT EXISTS org_role VARCHAR(20) DEFAULT 'member'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE user_agent_bindings DROP COLUMN IF EXISTS org_role")
