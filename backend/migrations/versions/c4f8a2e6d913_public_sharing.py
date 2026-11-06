"""public sharing of players, coaches and teams

Revision ID: c4f8a2e6d913
Revises: b7d3e9f1a265
Create Date: 2026-11-05 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8a2e6d913'
down_revision: Union[str, Sequence[str], None] = 'b7d3e9f1a265'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('players', 'coaches', 'teams')


def upgrade() -> None:
    """Upgrade schema. Everything starts private."""
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()))
            batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))
            batch_op.create_index(f'ix_{table}_is_public', ['is_public'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f'ix_{table}_is_public')
            batch_op.drop_column('published_at')
            batch_op.drop_column('is_public')
