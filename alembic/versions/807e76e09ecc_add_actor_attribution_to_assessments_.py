"""add actor attribution to assessments and incidents

Revision ID: 807e76e09ecc
Revises: b4e1c7a92f30
Create Date: 2026-09-15 02:11:25.696571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '807e76e09ecc'
down_revision: Union[str, Sequence[str], None] = 'b4e1c7a92f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite can't ALTER a constraint in place -- batch mode does copy-and-move instead.
    with op.batch_alter_table('assessment_records') as batch_op:
        batch_op.add_column(sa.Column('created_by_user_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_assessment_records_created_by_user_id', 'users', ['created_by_user_id'], ['id'])

    with op.batch_alter_table('incidents') as batch_op:
        batch_op.add_column(sa.Column('created_by_user_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('resolved_by_user_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_incidents_created_by_user_id', 'users', ['created_by_user_id'], ['id'])
        batch_op.create_foreign_key('fk_incidents_resolved_by_user_id', 'users', ['resolved_by_user_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('incidents') as batch_op:
        batch_op.drop_constraint('fk_incidents_resolved_by_user_id', type_='foreignkey')
        batch_op.drop_constraint('fk_incidents_created_by_user_id', type_='foreignkey')
        batch_op.drop_column('resolved_by_user_id')
        batch_op.drop_column('created_by_user_id')

    with op.batch_alter_table('assessment_records') as batch_op:
        batch_op.drop_constraint('fk_assessment_records_created_by_user_id', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')
