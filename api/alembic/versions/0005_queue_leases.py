from alembic import op
import sqlalchemy as sa


revision = "0005_queue_leases"
down_revision = "0004_tool_log_timestamp"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ingest_queue",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingest_queue",
        sa.Column("leased_until", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "ingest_queue",
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_ingest_queue_leased_until", "ingest_queue", ["leased_until"])


def downgrade():
    op.drop_index("idx_ingest_queue_leased_until", table_name="ingest_queue")
    op.drop_column("ingest_queue", "processed_at")
    op.drop_column("ingest_queue", "leased_until")
    op.drop_column("ingest_queue", "attempt_count")
