"""rematch

Revision ID: 9d4b7e2a6f18
Revises: c4f8a2e6d913
Create Date: 2026-11-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d4b7e2a6f18'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2e6d913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('blue_rematch_ready', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('red_rematch_ready', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('rematch_game_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_games_rematch_game_id_games', 'games', ['rematch_game_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_constraint('fk_games_rematch_game_id_games', type_='foreignkey')
        batch_op.drop_column('rematch_game_id')
        batch_op.drop_column('red_rematch_ready')
        batch_op.drop_column('blue_rematch_ready')
