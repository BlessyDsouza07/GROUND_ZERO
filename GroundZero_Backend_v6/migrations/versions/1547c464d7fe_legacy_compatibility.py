"""Compatibility bridge for the legacy database revision 1547c464d7fe.

The existing database may already be stamped at this revision even though the
revision file was missing from the integrated source tree.  Keep the revision
ID in the graph so Alembic can safely continue to the current head.
"""
from alembic import op  # noqa: F401

revision = "1547c464d7fe"
down_revision = "7796b31154e4"
branch_labels = None
depends_on = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
