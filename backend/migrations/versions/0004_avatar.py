"""Private immutable avatar files referenced by each account."""

from alembic import op

revision = "0004_avatar"
down_revision = "0003_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN avatar_key text")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_avatar_key "
        "CHECK (avatar_key ~ '^[0-9a-f]{32}\\.(jpg|png|webp)$')"
    )


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN avatar_key")
