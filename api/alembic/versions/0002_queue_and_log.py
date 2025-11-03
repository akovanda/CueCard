from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_queue_and_log"
down_revision = "0001_init_ctx_doc"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "ingest_queue",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("op_key", sa.String(length=256)),
        sa.Column("title", sa.String(length=256)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tags", sa.ARRAY(sa.String()), server_default="{}"),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("error_text", sa.Text, nullable=True),
    )
    op.create_index("idx_ingest_queue_status", "ingest_queue", ["status"])

    op.create_table(
        "tool_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("op_key", sa.String(length=256)),
        sa.Column("doc_id", sa.BigInteger),
        sa.Column("status", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
    )
    op.create_index("idx_tool_log_doc", "tool_log", ["doc_id"])

def downgrade():
    op.drop_index("idx_tool_log_doc", table_name="tool_log")
    op.drop_table("tool_log")
    op.drop_index("idx_ingest_queue_status", table_name="ingest_queue")
    op.drop_table("ingest_queue")
