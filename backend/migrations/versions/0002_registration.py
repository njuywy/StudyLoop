"""Account identity, single-use email verification and shared entry limits."""

from alembic import op

revision = "0002_registration"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE users (
            id uuid PRIMARY KEY,
            email text NOT NULL UNIQUE CHECK (email = lower(btrim(email))),
            password_hash text NOT NULL,
            nickname text NOT NULL CHECK (char_length(nickname) BETWEEN 1 AND 30),
            role text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
            email_verified boolean NOT NULL DEFAULT false,
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            verification_sent_at timestamptz
        )
    """)
    op.execute("""
        CREATE TABLE email_tokens (
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose text NOT NULL,
            digest text NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            PRIMARY KEY (user_id, purpose)
        )
    """)
    op.execute("""
        CREATE TABLE auth_rate_limits (
            key text PRIMARY KEY,
            attempts integer NOT NULL,
            expires_at timestamptz NOT NULL
        )
    """)
    op.execute("CREATE INDEX auth_rate_limits_expiry ON auth_rate_limits(expires_at)")


def downgrade():
    op.drop_table("auth_rate_limits")
    op.drop_table("email_tokens")
    op.drop_table("users")
