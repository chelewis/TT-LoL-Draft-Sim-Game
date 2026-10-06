"""riot rank

Revision ID: a7c41e9b2d53
Revises: 5c2f9a1d7e40
Create Date: 2026-10-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c41e9b2d53'
down_revision: Union[str, Sequence[str], None] = '5c2f9a1d7e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.add_column(sa.Column('riot_rank_queue', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('riot_rank_tier', sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column('riot_rank_division', sa.String(length=4), nullable=True))
        batch_op.add_column(sa.Column('riot_rank_lp', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('riot_rank_wins', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('riot_rank_losses', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_column('riot_rank_losses')
        batch_op.drop_column('riot_rank_wins')
        batch_op.drop_column('riot_rank_lp')
        batch_op.drop_column('riot_rank_division')
        batch_op.drop_column('riot_rank_tier')
        batch_op.drop_column('riot_rank_queue')
