"""agregar tabla clinical_entries

Revision ID: eca509748c67
Revises: 0ba170188fb3
Create Date: 2026-11-04 00:25:28.585463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eca509748c67'
down_revision: Union[str, Sequence[str], None] = '0ba170188fb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('clinical_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('clinic_id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=False),
    sa.Column('dentist_id', sa.Integer(), nullable=False),
    sa.Column('antecedentes', sa.Text(), nullable=True),
    sa.Column('motivo_consulta', sa.Text(), nullable=False),
    sa.Column('examen', sa.Text(), nullable=False),
    sa.Column('diagnostico', sa.Text(), nullable=False),
    sa.Column('tratamiento', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
    sa.ForeignKeyConstraint(['dentist_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clinical_entries_clinic_id'), 'clinical_entries', ['clinic_id'], unique=False)
    op.create_index(op.f('ix_clinical_entries_patient_id'), 'clinical_entries', ['patient_id'], unique=False)
    op.create_index(op.f('ix_clinical_entries_appointment_id'), 'clinical_entries', ['appointment_id'], unique=True)
    op.create_index(op.f('ix_clinical_entries_dentist_id'), 'clinical_entries', ['dentist_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_clinical_entries_dentist_id'), table_name='clinical_entries')
    op.drop_index(op.f('ix_clinical_entries_appointment_id'), table_name='clinical_entries')
    op.drop_index(op.f('ix_clinical_entries_patient_id'), table_name='clinical_entries')
    op.drop_index(op.f('ix_clinical_entries_clinic_id'), table_name='clinical_entries')
    op.drop_table('clinical_entries')