"""draft hover

Revision ID: c5d1e7a3f290
Revises: b8e4d2f6a913
Create Date: 2026-10-18 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d1e7a3f290'
down_revision: Union[str, Sequence[str], None] = 'b8e4d2f6a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('games', sa.Column('hovered_champion_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('games', 'hovered_champion_id')
