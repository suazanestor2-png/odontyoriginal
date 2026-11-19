"""cifrar secreto mfa

Revision ID: beb6ee8ace73
Revises: 1c494da5a176
Create Date: 2026-11-18 23:19:34.769906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'beb6ee8ace73'
down_revision: Union[str, Sequence[str], None] = '1c494da5a176'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Amplia la columna (el texto cifrado ocupa mas que el secreto base32)
    op.alter_column("users", "mfa_secret", existing_type=sa.String(length=64),
                    type_=sa.String(length=255), existing_nullable=True)
    # Cifra los secretos que estaban en texto plano
    from app.core.security import encrypt_mfa_secret
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, mfa_secret FROM users WHERE mfa_secret IS NOT NULL")).fetchall()
    for user_id, secret in rows:
        if secret.startswith("gAAAAA"):  # ya esta cifrado con Fernet
            continue
        conn.execute(sa.text("UPDATE users SET mfa_secret = :s WHERE id = :i"),
                     {"s": encrypt_mfa_secret(secret), "i": user_id})


def downgrade() -> None:
    from app.core.security import decrypt_mfa_secret
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, mfa_secret FROM users WHERE mfa_secret IS NOT NULL")).fetchall()
    for user_id, token in rows:
        conn.execute(sa.text("UPDATE users SET mfa_secret = :s WHERE id = :i"),
                     {"s": decrypt_mfa_secret(token), "i": user_id})
    op.alter_column("users", "mfa_secret", existing_type=sa.String(length=255),
                    type_=sa.String(length=64), existing_nullable=True)
