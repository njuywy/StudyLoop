"""Independent bookmarks and manual mastery states."""

from alembic import op

revision = "0007_review_states"
down_revision = "0006_reading_position"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE review_states (
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        point_id text NOT NULL REFERENCES review_points(id) ON DELETE CASCADE,
        bookmarked boolean NOT NULL DEFAULT false,
        mastery text NOT NULL DEFAULT 'unlearned'
            CHECK (mastery IN ('unlearned','needs_review','mastered')),
        revision bigint NOT NULL CHECK (revision > 0), PRIMARY KEY(user_id,point_id)
    )""")
    op.execute("""CREATE TABLE review_state_operations (
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        point_id text NOT NULL REFERENCES review_points(id) ON DELETE CASCADE,
        operation_id uuid NOT NULL, request jsonb NOT NULL, response jsonb NOT NULL,
        PRIMARY KEY(user_id,point_id,operation_id)
    )""")


def downgrade():
    op.execute("DROP TABLE review_state_operations")
    op.execute("DROP TABLE review_states")
