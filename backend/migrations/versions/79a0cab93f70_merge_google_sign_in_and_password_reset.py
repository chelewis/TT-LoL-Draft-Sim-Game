"""merge google sign-in and password reset

Revision ID: 79a0cab93f70
Revises: a1f6c3e8d572, b61d3f0a9c27
Create Date: 2026-10-23 12:14:31.065706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79a0cab93f70'
down_revision: Union[str, Sequence[str], None] = ('a1f6c3e8d572', 'b61d3f0a9c27')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
