"""Initial baseline migration - marks the current schema as baseline.
This migration intentionally does not alter schema; it's a no-op baseline so future Alembic revisions start from this point.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depend_on = None


def upgrade():
    # Baseline migration - no schema changes performed here.
    pass


def downgrade():
    pass
