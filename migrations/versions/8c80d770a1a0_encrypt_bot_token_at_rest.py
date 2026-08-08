"""encrypt bot_token at rest

Revision ID: 8c80d770a1a0
Revises: 4a33d86c0ce1
Create Date: 2026-08-04 10:53:15.997061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c80d770a1a0'
down_revision: Union[str, Sequence[str], None] = '4a33d86c0ce1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавить bot_token_hash, зашифровать существующие токены."""
    import logging

    from app.utils.crypto import encrypt, token_hash

    log = logging.getLogger(__name__)

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("bot_token_hash", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_shops_bot_token_hash", ["bot_token_hash"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, bot_token FROM shops")).fetchall()

    for row in rows:
        shop_id = row[0]
        raw_token = row[1]

        if raw_token.startswith("gAAAAA"):
            log.info("Shop %d: токен уже зашифрован, пропуск", shop_id)
            continue

        encrypted = encrypt(raw_token)
        hashed = token_hash(raw_token)
        conn.execute(
            sa.text(
                "UPDATE shops SET bot_token = :enc, bot_token_hash = :h "
                "WHERE id = :id"
            ),
            {"enc": encrypted, "h": hashed, "id": shop_id},
        )
        log.info("Shop %d: токен зашифрован", shop_id)


def downgrade() -> None:
    """Удалить bot_token_hash, расшифровать токены."""
    from app.utils.crypto import decrypt

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, bot_token FROM shops")).fetchall()

    for row in rows:
        shop_id = row[0]
        token = row[1]
        if token.startswith("gAAAAA"):
            plaintext = decrypt(token)
            if plaintext:
                conn.execute(
                    sa.text("UPDATE shops SET bot_token = :t WHERE id = :id"),
                    {"t": plaintext, "id": shop_id},
                )

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_constraint("uq_shops_bot_token_hash", type_="unique")
        batch_op.drop_column("bot_token_hash")
