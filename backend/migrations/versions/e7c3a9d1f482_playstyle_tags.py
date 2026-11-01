"""playstyle tags

Revision ID: e7c3a9d1f482
Revises: 79a0cab93f70
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e7c3a9d1f482'
down_revision: Union[str, Sequence[str], None] = '79a0cab93f70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    """Upgrade schema. The starter tags are added by the app's seeding when the table is empty."""
    # a development server's create_all may already have made this new table (it never alters existing ones)
    if not sa.inspect(op.get_bind()).has_table('playstyle_tags'):
        _create_tags_table()
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.add_column(sa.Column('riot_earned_tags', JSON, nullable=True))
        batch_op.add_column(sa.Column('playstyle_tags', JSON, nullable=True))


def _create_tags_table() -> None:
    op.create_table(
        'playstyle_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=32), nullable=False),
        sa.Column('label', sa.String(length=40), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('polarity', sa.String(length=8), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('rule', JSON, nullable=False),
        sa.Column('effects', JSON, nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_column('playstyle_tags')
        batch_op.drop_column('riot_earned_tags')
    op.drop_table('playstyle_tags')
