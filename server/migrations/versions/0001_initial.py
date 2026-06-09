"""initial gymbox schema

Creates the `gymbox` schema and all tables, then seeds the 13 annotation
layers. To stay drift-proof, table creation reuses the ORM's own metadata
(Base.metadata.create_all) rather than hand-written op.create_table calls — the
models in gymbox/persistence/models.py are the single source of truth
(architecture.md §9). The layer seed pulls from the canonical ANNOTATION_LAYERS
list so the 13 layers can never disagree with the code.

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSchema, DropSchema

from gymbox.persistence import ANNOTATION_LAYERS
from gymbox.persistence.models import SCHEMA, Base

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Schema.
    op.execute(CreateSchema(SCHEMA, if_not_exists=True))

    # 2. All tables, straight from the ORM metadata (no drift possible).
    Base.metadata.create_all(bind=bind)

    # 3. Seed the 13 annotation layers (architecture.md §9). The annotations
    #    table FKs to these, so they must exist before any upload.
    layers = sa.table(
        "annotation_layers",
        sa.column("id", sa.String),
        sa.column("description", sa.String),
        sa.column("allowed_values", sa.JSON),
        schema=SCHEMA,
    )
    op.bulk_insert(
        layers,
        [
            {
                "id": layer["id"],
                "description": layer.get("description"),
                "allowed_values": layer.get("allowed_values"),
            }
            for layer in ANNOTATION_LAYERS
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    op.execute(DropSchema(SCHEMA, cascade=True, if_exists=True))
