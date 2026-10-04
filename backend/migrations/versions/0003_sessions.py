"""Revocable bearer sessions for verified accounts."""

from alembic import op

revision = "0003_sessions"
down_revision = "0002_registration"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE auth_sessions (
            digest text PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX auth_sessions_user_id ON auth_sessions(user_id)")
    op.execute("""
        CREATE FUNCTION revoke_sessions_on_account_inactive() RETURNS trigger AS $$
        BEGIN
            IF (OLD.enabled AND NOT NEW.enabled)
               OR (OLD.email_verified AND NOT NEW.email_verified) THEN
                UPDATE auth_sessions SET revoked_at = now()
                WHERE user_id = NEW.id AND revoked_at IS NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER users_revoke_sessions_on_inactive
        AFTER UPDATE OF enabled, email_verified ON users
        FOR EACH ROW EXECUTE FUNCTION revoke_sessions_on_account_inactive()
    """)


def downgrade():
    op.execute("DROP TRIGGER users_revoke_sessions_on_inactive ON users")
    op.execute("DROP FUNCTION revoke_sessions_on_account_inactive()")
    op.drop_table("auth_sessions")
