"""champion edited fields

Revision ID: b7d3e9f1a265
Revises: e4a9c2f7b813
Create Date: 2026-11-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d3e9f1a265'
down_revision: Union[str, Sequence[str], None] = 'e4a9c2f7b813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # columns an admin has edited ("pick_rate|win_rate"); the seed sync skips them
    with op.batch_alter_table('champions') as batch:
        batch.add_column(sa.Column('edited_fields', sa.String(length=256), nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('champions') as batch:
        batch.drop_column('edited_fields')
