from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_voting_and_boosts"
down_revision = "0002_queue_and_log"
branch_labels = None
depends_on = None

def upgrade():
    # Create doc_vote table for permanent boosts
    op.create_table(
        "doc_vote",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("doc_id", sa.BigInteger, nullable=False),
        sa.Column("vote_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_doc_vote_doc_id", "doc_vote", ["doc_id"], unique=True)

    # Create doc_usage_boost table for temporary boosts
    op.create_table(
        "doc_usage_boost",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("doc_id", sa.BigInteger, nullable=False),
        sa.Column("boost_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("idx_doc_usage_boost_doc_id", "doc_usage_boost", ["doc_id"])
    op.create_index("idx_doc_usage_boost_expires", "doc_usage_boost", ["expires_at"])

def downgrade():
    op.drop_index("idx_doc_usage_boost_expires", table_name="doc_usage_boost")
    op.drop_index("idx_doc_usage_boost_doc_id", table_name="doc_usage_boost")
    op.drop_table("doc_usage_boost")
    op.drop_index("idx_doc_vote_doc_id", table_name="doc_vote")
    op.drop_table("doc_vote")
