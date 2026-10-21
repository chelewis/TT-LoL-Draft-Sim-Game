"""champion scaling

Revision ID: d4a8e2c6b157
Revises: c5d1e7a3f290
Create Date: 2026-10-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a8e2c6b157'
down_revision: Union[str, Sequence[str], None] = 'c5d1e7a3f290'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1 early game, 2 neutral, 3 late game; the seed sync fills in real values on the next start
    op.add_column('champions', sa.Column('scaling', sa.Integer(), nullable=False, server_default='2'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('champions', 'scaling')
