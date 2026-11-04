"""agregar tabla appointments y horario de clinica

Revision ID: 0ba170188fb3
Revises: 7c57b1e648d0
Create Date: 2026-11-03 16:09:16.968336

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ba170188fb3'
down_revision: Union[str, Sequence[str], None] = '7c57b1e648d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clinics', sa.Column('opening_time', sa.Time(), nullable=False, server_default='08:00:00'))
    op.add_column('clinics', sa.Column('closing_time', sa.Time(), nullable=False, server_default='18:00:00'))
    op.add_column('clinics', sa.Column('working_days', sa.String(length=20), nullable=False, server_default='1,2,3,4,5,6'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clinics', 'working_days')
    op.drop_column('clinics', 'closing_time')
    op.drop_column('clinics', 'opening_time')
