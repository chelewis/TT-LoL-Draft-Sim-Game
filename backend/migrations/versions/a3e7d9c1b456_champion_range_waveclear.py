"""champion range and waveclear

Revision ID: a3e7d9c1b456
Revises: f9b2d4e6a1c3
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3e7d9c1b456'
down_revision: Union[str, Sequence[str], None] = 'f9b2d4e6a1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # both 1 to 3; the seed sync fills in real values on the next start
    op.add_column('champions', sa.Column('attack_range', sa.Integer(), nullable=False, server_default='2'))
    op.add_column('champions', sa.Column('waveclear', sa.Integer(), nullable=False, server_default='2'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('champions', 'waveclear')
    op.drop_column('champions', 'attack_range')
