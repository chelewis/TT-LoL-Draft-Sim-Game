"""champion matchups

Revision ID: c3d9f1a47b62
Revises: a7c41e9b2d53
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d9f1a47b62'
down_revision: Union[str, Sequence[str], None] = 'a7c41e9b2d53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'champion_matchups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('champion_a_id', sa.Integer(), nullable=False),
        sa.Column('champion_b_id', sa.Integer(), nullable=False),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('wins', sa.Integer(), nullable=False),
        sa.Column('edited', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['champion_a_id'], ['champions.id']),
        sa.ForeignKeyConstraint(['champion_b_id'], ['champions.id']),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'champion_a_id', 'champion_b_id'),
    )
    with op.batch_alter_table('champion_matchups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_champion_matchups_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_champion_matchups_champion_a_id'), ['champion_a_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_champion_matchups_champion_b_id'), ['champion_b_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('champion_matchups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_champion_matchups_champion_b_id'))
        batch_op.drop_index(batch_op.f('ix_champion_matchups_champion_a_id'))
        batch_op.drop_index(batch_op.f('ix_champion_matchups_kind'))
    op.drop_table('champion_matchups')
