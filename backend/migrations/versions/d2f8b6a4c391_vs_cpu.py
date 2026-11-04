"""vs cpu games

Revision ID: d2f8b6a4c391
Revises: a3e7d9c1b456
Create Date: 2026-11-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2f8b6a4c391'
down_revision: Union[str, Sequence[str], None] = 'a3e7d9c1b456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vs_cpu', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_column('vs_cpu')
