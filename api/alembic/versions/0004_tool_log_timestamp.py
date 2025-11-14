from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_tool_log_timestamp"
down_revision = "0003_voting_and_boosts"
branch_labels = None
depends_on = None


def upgrade():
    # Add created_at timestamp to tool_log for time-range queries
    op.add_column(
        "tool_log",
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_tool_log_created_at", "tool_log", ["created_at"])  # helpful for range scans


def downgrade():
    op.drop_index("idx_tool_log_created_at", table_name="tool_log")
    op.drop_column("tool_log", "created_at")

