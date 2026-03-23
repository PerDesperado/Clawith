"""Add must_change_password field to users table.

Revision ID: add_must_change_password
Revises: rebuild_org_hierarchy
Create Date: 2024-01-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_must_change_password'
down_revision: Union[str, None] = 'rebuild_org_hierarchy'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add must_change_password column to users table
    op.add_column(
        'users',
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
