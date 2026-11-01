"""riot import seal

Revision ID: f9b2d4e6a1c3
Revises: e7c3a9d1f482
Create Date: 2026-11-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9b2d4e6a1c3'
down_revision: Union[str, Sequence[str], None] = 'e7c3a9d1f482'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Players imported before this have no seal and show as unverified until refreshed."""
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.add_column(sa.Column('riot_seal', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('players', schema=None) as batch_op:
        batch_op.drop_column('riot_seal')
