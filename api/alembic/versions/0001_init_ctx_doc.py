from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "0001_init_ctx_doc"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ctx_doc",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("op_key", sa.String(length=256), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tags", sa.ARRAY(sa.String()), server_default="{}", nullable=True),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_ctx_doc_opkey", "ctx_doc", ["op_key"])
    op.create_index("idx_ctx_doc_tags", "ctx_doc", ["tags"], postgresql_using="gin")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ctx_doc_embedding_hnsw
        ON ctx_doc USING hnsw (embedding vector_cosine_ops)
    """)

def downgrade():
    op.drop_index("idx_ctx_doc_embedding_hnsw", table_name="ctx_doc")
    op.drop_index("idx_ctx_doc_tags", table_name="ctx_doc")
    op.drop_index("idx_ctx_doc_opkey", table_name="ctx_doc")
    op.drop_table("ctx_doc")
    op.execute("DROP EXTENSION IF EXISTS vector")
