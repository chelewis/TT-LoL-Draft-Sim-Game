"""season player draft and free agency

Revision ID: b5d1f3a7c9e2
Revises: a2c6e8f0b4d1
Create Date: 2026-11-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d1f3a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'a2c6e8f0b4d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # a dev server's create_all may already have made the new tables (it never adds columns to existing ones)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('season_draft_picks'):
        op.create_table(
            'season_draft_picks',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('pick_number', sa.Integer(), nullable=False),
            sa.Column('season_team_id', sa.Integer(), nullable=False),
            sa.Column('player_id', sa.Integer(), nullable=True),
            sa.Column('lane', sa.String(length=10), nullable=False),
            sa.Column('auto', sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['season_team_id'], ['season_teams.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('season_id', 'pick_number'),
        )
        op.create_index(op.f('ix_season_draft_picks_season_id'), 'season_draft_picks', ['season_id'], unique=False)
    if not inspector.has_table('season_transactions'):
        op.create_table(
            'season_transactions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=False),
            sa.Column('season_team_id', sa.Integer(), nullable=False),
            sa.Column('type', sa.String(length=8), nullable=False),
            sa.Column('player_id', sa.Integer(), nullable=True),
            sa.Column('player_name', sa.String(length=40), nullable=False),
            sa.Column('lane', sa.String(length=10), nullable=False),
            sa.Column('stage', sa.String(length=8), nullable=False),
            sa.Column('round', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['season_team_id'], ['season_teams.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_season_transactions_season_id'), 'season_transactions', ['season_id'], unique=False)
        op.create_index(op.f('ix_season_transactions_season_team_id'), 'season_transactions', ['season_team_id'],
                        unique=False)
    with op.batch_alter_table('seasons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pick_deadline_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('season_teams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('draft_position', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('season_teams', schema=None) as batch_op:
        batch_op.drop_column('draft_position')
    with op.batch_alter_table('seasons', schema=None) as batch_op:
        batch_op.drop_column('pick_deadline_at')
    op.drop_index(op.f('ix_season_transactions_season_team_id'), table_name='season_transactions')
    op.drop_index(op.f('ix_season_transactions_season_id'), table_name='season_transactions')
    op.drop_table('season_transactions')
    op.drop_index(op.f('ix_season_draft_picks_season_id'), table_name='season_draft_picks')
    op.drop_table('season_draft_picks')
