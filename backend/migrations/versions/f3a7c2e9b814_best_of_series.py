"""best of series and fearless draft

Revision ID: f3a7c2e9b814
Revises: e5b8a2c41f09
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a7c2e9b814'
down_revision: Union[str, Sequence[str], None] = 'e5b8a2c41f09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # a dev server's create_all may already have made the new table (it never adds columns, so games still needs them)
    if not sa.inspect(op.get_bind()).has_table('series'):
        _create_series()
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('series_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('game_number', sa.Integer(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('sides_swapped', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('blue_next_ready', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('red_next_ready', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('next_loser_side', sa.String(length=4), nullable=True))
        batch_op.create_index(batch_op.f('ix_games_series_id'), ['series_id'], unique=False)
        batch_op.create_foreign_key('fk_games_series_id_series', 'series', ['series_id'], ['id'])
        batch_op.create_unique_constraint('uq_games_series_id_game_number', ['series_id', 'game_number'])


def _create_series() -> None:
    op.create_table(
        'series',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('format', sa.String(length=4), nullable=False),
        sa.Column('wins_needed', sa.Integer(), nullable=False),
        sa.Column('fearless', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_constraint('uq_games_series_id_game_number', type_='unique')
        batch_op.drop_constraint('fk_games_series_id_series', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_games_series_id'))
        batch_op.drop_column('next_loser_side')
        batch_op.drop_column('red_next_ready')
        batch_op.drop_column('blue_next_ready')
        batch_op.drop_column('sides_swapped')
        batch_op.drop_column('game_number')
        batch_op.drop_column('series_id')
    op.drop_table('series')
