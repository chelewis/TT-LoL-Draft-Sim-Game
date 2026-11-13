"""notifications and season deadline warnings

Revision ID: c8e2a4f6d071
Revises: b5d1f3a7c9e2
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8e2a4f6d071'
down_revision: Union[str, Sequence[str], None] = 'b5d1f3a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # a dev server's create_all may already have made the new table (it never adds columns to existing ones)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('kind', sa.String(length=24), nullable=False),
            sa.Column('title', sa.String(length=120), nullable=False),
            sa.Column('body', sa.String(length=300), nullable=False),
            sa.Column('link', sa.String(length=200), nullable=False),
            sa.Column('season_id', sa.Integer(), nullable=True),
            sa.Column('key', sa.String(length=80), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('read_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'key'),
        )
        op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
        op.create_index(op.f('ix_notifications_season_id'), 'notifications', ['season_id'], unique=False)
        op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    with op.batch_alter_table('seasons', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deadline_warned', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('seasons', schema=None) as batch_op:
        batch_op.drop_column('deadline_warned')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_season_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
