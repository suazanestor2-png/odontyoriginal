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
    # Horario de la clinica
    op.add_column('clinics', sa.Column('opening_time', sa.Time(), nullable=False, server_default='08:00:00'))
    op.add_column('clinics', sa.Column('closing_time', sa.Time(), nullable=False, server_default='18:00:00'))
    op.add_column('clinics', sa.Column('working_days', sa.String(length=20), nullable=False, server_default='1,2,3,4,5,6'))

    # Tabla de citas (faltaba: en local la habia creado create_all)
    op.create_table('appointments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('clinic_id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('dentist_id', sa.Integer(), nullable=False),
    sa.Column('scheduled_date', sa.Date(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('end_time', sa.Time(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('origin', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('cancellation_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
    sa.ForeignKeyConstraint(['dentist_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_appointments_created_by', use_alter=True),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_appointments_updated_by', use_alter=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_appointments_clinic_id'), 'appointments', ['clinic_id'], unique=False)
    op.create_index(op.f('ix_appointments_patient_id'), 'appointments', ['patient_id'], unique=False)
    op.create_index(op.f('ix_appointments_dentist_id'), 'appointments', ['dentist_id'], unique=False)
    op.create_index(op.f('ix_appointments_scheduled_date'), 'appointments', ['scheduled_date'], unique=False)
    op.create_index(op.f('ix_appointments_status'), 'appointments', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_appointments_status'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_scheduled_date'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_dentist_id'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_patient_id'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_clinic_id'), table_name='appointments')
    op.drop_table('appointments')

    op.drop_column('clinics', 'working_days')
    op.drop_column('clinics', 'closing_time')
    op.drop_column('clinics', 'opening_time')