"""Versioned private reading material and stable knowledge points."""

from alembic import op

revision = "0005_review_content"
down_revision = "0004_avatar"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE review_books (
        id text PRIMARY KEY, metadata jsonb NOT NULL, toc jsonb NOT NULL,
        storage_key text NOT NULL, pages jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE review_points (
        id text PRIMARY KEY, book_id text NOT NULL REFERENCES review_books(id),
        ordinal integer NOT NULL, document jsonb NOT NULL,
        UNIQUE(book_id, ordinal)
    )""")


def downgrade():
    op.execute("DROP TABLE review_points")
    op.execute("DROP TABLE review_books")
