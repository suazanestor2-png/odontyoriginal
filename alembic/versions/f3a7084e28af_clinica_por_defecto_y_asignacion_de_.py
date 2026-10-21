"""clinica por defecto y asignacion de usuarios

Revision ID: f3a7084e28af
Revises: e6038c18674c
Create Date: 2026-10-18 13:30:52.844657

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a7084e28af'
down_revision: Union[str, Sequence[str], None] = 'e6038c18674c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO clinics (name, status, timezone, created_at, updated_at)
        VALUES ('Clinica Principal', 'approved', 'America/Bogota', now(), now())
    """))
    conn.execute(sa.text("""
        UPDATE users SET clinic_id = (SELECT id FROM clinics ORDER BY id LIMIT 1)
        WHERE clinic_id IS NULL
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET clinic_id = NULL"))
    conn.execute(sa.text("DELETE FROM clinics"))
