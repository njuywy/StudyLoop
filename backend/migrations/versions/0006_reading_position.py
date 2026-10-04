"""Per-account reading position and idempotent writes."""

from alembic import op

revision = "0006_reading_position"
down_revision = "0005_review_content"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE review_positions (
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        book_id text NOT NULL REFERENCES review_books(id) ON DELETE CASCADE,
        position jsonb NOT NULL, PRIMARY KEY(user_id, book_id)
    )""")
    op.execute("""CREATE TABLE review_position_operations (
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        book_id text NOT NULL REFERENCES review_books(id) ON DELETE CASCADE,
        operation_id uuid NOT NULL, request jsonb NOT NULL, response jsonb NOT NULL,
        PRIMARY KEY(user_id, book_id, operation_id)
    )""")


def downgrade():
    op.execute("DROP TABLE review_position_operations")
    op.execute("DROP TABLE review_positions")
