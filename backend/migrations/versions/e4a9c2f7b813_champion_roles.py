"""champion roles

Revision ID: e4a9c2f7b813
Revises: d2f8b6a4c391
Create Date: 2026-11-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a9c2f7b813'
down_revision: Union[str, Sequence[str], None] = 'd2f8b6a4c391'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # usual lanes, most played first ("JUNGLE|TOP"); the seed sync fills in real values on the next start
    with op.batch_alter_table('champions') as batch:
        batch.add_column(sa.Column('roles', sa.String(length=64), nullable=False, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('champions') as batch:
        batch.drop_column('roles')
