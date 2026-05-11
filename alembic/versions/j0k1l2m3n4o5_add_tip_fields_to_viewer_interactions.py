"""add tip_amount and tip_currency to viewer_interactions

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-05-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, Sequence[str], None] = 'i9j0k1l2m3n4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('viewer_interactions', sa.Column('tip_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('viewer_interactions', sa.Column('tip_currency', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('viewer_interactions', 'tip_currency')
    op.drop_column('viewer_interactions', 'tip_amount')
