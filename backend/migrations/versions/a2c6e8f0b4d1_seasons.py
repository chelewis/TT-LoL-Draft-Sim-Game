"""seasons: leagues and tournaments

Revision ID: a2c6e8f0b4d1
Revises: 9d4b7e2a6f18
Create Date: 2026-11-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a2c6e8f0b4d1'
down_revision: Union[str, Sequence[str], None] = '9d4b7e2a6f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')
CONTENT_TABLES = ('coaches', 'players', 'teams')


def upgrade() -> None:
    """Upgrade schema."""
    # a dev server's create_all may already have made the new tables (it never adds columns to existing ones)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('seasons'):
        _create_seasons()
    if not inspector.has_table('season_teams'):
        _create_season_teams()
    if not inspector.has_table('season_matches'):
        _create_season_matches()
    for table in CONTENT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f(f'ix_{table}_season_id'), ['season_id'], unique=False)
            batch_op.create_foreign_key(f'fk_{table}_season_id_seasons', 'seasons', ['season_id'], ['id'],
                                        ondelete='CASCADE')
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_match_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_games_season_match_id'), ['season_match_id'], unique=False)
        batch_op.create_foreign_key('fk_games_season_match_id_season_matches', 'season_matches',
                                    ['season_match_id'], ['id'])


def _create_seasons() -> None:
    op.create_table(
        'seasons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('code', sa.String(length=6), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('roster_mode', sa.String(length=8), nullable=False),
        sa.Column('format', sa.String(length=12), nullable=False),
        sa.Column('settings', JSON, nullable=False),
        sa.Column('current_round', sa.Integer(), nullable=False),
        sa.Column('round_deadline_at', sa.DateTime(), nullable=True),
        sa.Column('winner_team_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_seasons_code'), 'seasons', ['code'], unique=True)
    op.create_index(op.f('ix_seasons_created_by'), 'seasons', ['created_by'], unique=False)
    op.create_index(op.f('ix_seasons_status'), 'seasons', ['status'], unique=False)


def _create_season_teams() -> None:
    op.create_table(
        'season_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('manager_user_id', sa.Integer(), nullable=True),
        sa.Column('seed', sa.Integer(), nullable=False),
        sa.Column('eliminated', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manager_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('season_id', 'team_id'),
    )
    op.create_index(op.f('ix_season_teams_season_id'), 'season_teams', ['season_id'], unique=False)
    op.create_index(op.f('ix_season_teams_manager_user_id'), 'season_teams', ['manager_user_id'], unique=False)


def _create_season_matches() -> None:
    op.create_table(
        'season_matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=8), nullable=False),
        sa.Column('round', sa.Integer(), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('format', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('played_mode', sa.String(length=4), nullable=True),
        sa.Column('series_id', sa.Integer(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=False),
        sa.Column('away_score', sa.Integer(), nullable=False),
        sa.Column('winner_team_id', sa.Integer(), nullable=True),
        sa.Column('home_auto_ready', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('away_auto_ready', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['home_team_id'], ['season_teams.id']),
        sa.ForeignKeyConstraint(['away_team_id'], ['season_teams.id']),
        sa.ForeignKeyConstraint(['winner_team_id'], ['season_teams.id']),
        sa.ForeignKeyConstraint(['series_id'], ['series.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_season_matches_season_id'), 'season_matches', ['season_id'], unique=False)
    op.create_index(op.f('ix_season_matches_status'), 'season_matches', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_constraint('fk_games_season_match_id_season_matches', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_games_season_match_id'))
        batch_op.drop_column('season_match_id')
    for table in CONTENT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{table}_season_id_seasons', type_='foreignkey')
            batch_op.drop_index(batch_op.f(f'ix_{table}_season_id'))
            batch_op.drop_column('season_id')
    op.drop_table('season_matches')
    op.drop_table('season_teams')
    op.drop_table('seasons')
