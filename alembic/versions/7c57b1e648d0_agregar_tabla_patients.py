"""agregar tabla patients

Revision ID: 7c57b1e648d0
Revises: df5a51d873ca
Create Date: 2026-10-29 01:13:38.365007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c57b1e648d0'
down_revision: Union[str, Sequence[str], None] = 'df5a51d873ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('patients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('clinic_id', sa.Integer(), nullable=False),
    sa.Column('document_type', sa.String(length=2), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('gender', sa.String(length=20), nullable=True),
    sa.Column('blood_type', sa.String(length=3), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('eps', sa.String(length=100), nullable=True),
    sa.Column('guardian_full_name', sa.String(length=150), nullable=True),
    sa.Column('guardian_document_number', sa.String(length=20), nullable=True),
    sa.Column('guardian_phone', sa.String(length=20), nullable=True),
    sa.Column('guardian_relationship', sa.String(length=50), nullable=True),
    sa.Column('emergency_contact_name', sa.String(length=150), nullable=True),
    sa.Column('emergency_contact_phone', sa.String(length=20), nullable=True),
    sa.Column('allergies', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_patients_created_by', use_alter=True),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='fk_patients_updated_by', use_alter=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patients_user_id'), 'patients', ['user_id'], unique=True)
    op.create_index(op.f('ix_patients_clinic_id'), 'patients', ['clinic_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_patients_clinic_id'), table_name='patients')
    op.drop_index(op.f('ix_patients_user_id'), table_name='patients')
    op.drop_table('patients')