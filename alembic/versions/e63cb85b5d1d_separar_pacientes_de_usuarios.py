"""separar pacientes de usuarios

Revision ID: e63cb85b5d1d
Revises: e4dc2ea725a1
Create Date: 2026-11-13 09:16:07.986711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e63cb85b5d1d'
down_revision: Union[str, Sequence[str], None] = 'e4dc2ea725a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Columnas nuevas del paciente (temporalmente opcionales para poder llenarlas)
    op.add_column("patients", sa.Column("full_name", sa.String(150), nullable=True))
    op.add_column("patients", sa.Column("document_number", sa.String(20), nullable=True))
    op.add_column("patients", sa.Column("email", sa.String(255), nullable=True))
    op.add_column("patients", sa.Column("phone_number", sa.String(20), nullable=True))

    # 2. Copiar los datos personales desde la cuenta de usuario a la que apuntaba cada paciente
    op.execute(
        """
        UPDATE patients p
        SET full_name       = u.full_name,
            document_number = u.document_number,
            email           = u.email,
            phone_number    = COALESCE(u.phone_number, '')
        FROM users u
        WHERE p.user_id = u.id
        """
    )

    # 3. Ahora si, obligatorios
    op.alter_column("patients", "full_name", nullable=False)
    op.alter_column("patients", "document_number", nullable=False)
    op.alter_column("patients", "email", nullable=False)
    op.alter_column("patients", "phone_number", nullable=False)

    # 4. Las cuentas de pacientes (rol "usuario") ya no se usan: se desactivan
    op.execute(
        """
        UPDATE users
        SET is_active = false
        WHERE role_id IN (SELECT id FROM roles WHERE name = 'usuario')
        """
    )

    # 5. Romper el vinculo paciente -> usuario
    op.drop_constraint("uq_patients_user_id_clinic_id", "patients", type_="unique")
    op.drop_index(op.f("ix_patients_user_id"), table_name="patients")
    op.drop_column("patients", "user_id")

    # 6. Un paciente es unico por documento dentro de cada clinica
    op.create_index(op.f("ix_patients_document_number"), "patients", ["document_number"], unique=False)
    op.create_unique_constraint(
        "uq_patients_clinic_document", "patients", ["clinic_id", "document_type", "document_number"]
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Esta migracion no se puede revertir: los pacientes ya no estan ligados a cuentas de usuario."
    )