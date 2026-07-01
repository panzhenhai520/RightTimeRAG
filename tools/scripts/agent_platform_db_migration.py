#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
"""
Agent platform database migration script.

This script makes the current agent-platform schema requirements explicit for
deployments that need a manual migration step. It is intentionally idempotent:
missing agent-related tables can be created with Peewee's safe mode, and missing
columns are added only after checking the live database schema.

Runtime data that is not modeled as SQL tables is not migrated here:
- agent task planning state is currently process-local memory;
- agent run state/events are stored in Redis;
- workspace files are stored in the managed filesystem workspace.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from peewee import BooleanField, CharField, Field, IntegerField, TextField
from playhouse.migrate import migrate

PROJECT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_BASE)

from api.db import db_models  # noqa: E402
from api.db.db_models import DB, JSONField, ListField  # noqa: E402
from common import settings  # noqa: E402


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnMigration:
    table: str
    column: str
    field_factory: Callable[[], Field]
    reason: str


@dataclass(frozen=True)
class ColumnTypeMigration:
    table: str
    column: str
    field_factory: Callable[[], Field]
    target_data_types: tuple[str, ...]
    reason: str


AGENT_RELATED_MODELS = [
    db_models.UserCanvas,
    db_models.UserCanvasVersion,
    db_models.CanvasTemplate,
    db_models.MCPServer,
    db_models.API4Conversation,
    db_models.APIToken,
    db_models.Dialog,
    db_models.LLM,
    db_models.Memory,
    db_models.SystemSettings,
]


COLUMN_MIGRATIONS = [
    ColumnMigration(
        "api_token",
        "source",
        lambda: CharField(max_length=16, null=True, help_text="none|agent|dialog", index=True),
        "marks API tokens that belong to agents or dialog apps",
    ),
    ColumnMigration(
        "api_4_conversation",
        "source",
        lambda: CharField(max_length=16, null=True, help_text="none|agent|dialog", index=True),
        "records whether a published API conversation came from an agent",
    ),
    ColumnMigration(
        "api_4_conversation",
        "dsl",
        lambda: JSONField(null=True, default={}),
        "stores the agent DSL snapshot used by a published run",
    ),
    ColumnMigration(
        "api_4_conversation",
        "errors",
        lambda: TextField(null=True, help_text="errors"),
        "keeps agent publish/run validation errors with API conversation records",
    ),
    ColumnMigration(
        "api_4_conversation",
        "name",
        lambda: CharField(max_length=255, null=True, help_text="conversation name", index=False),
        "stores a readable session name for agent conversations",
    ),
    ColumnMigration(
        "api_4_conversation",
        "exp_user_id",
        lambda: CharField(max_length=255, null=True, help_text="exp_user_id", index=True),
        "keeps external user identity for published agent sessions",
    ),
    ColumnMigration(
        "api_4_conversation",
        "version_title",
        lambda: CharField(max_length=255, null=True, help_text="canvas version title when session created", index=False),
        "records the published agent version title used by a session",
    ),
    ColumnMigration(
        "user_canvas",
        "permission",
        lambda: CharField(max_length=16, null=False, help_text="me|team", default="me", index=True),
        "supports agent visibility control",
    ),
    ColumnMigration(
        "user_canvas",
        "release",
        lambda: BooleanField(null=False, help_text="is released", default=False, index=True),
        "tracks whether an agent canvas has been published",
    ),
    ColumnMigration(
        "user_canvas",
        "canvas_category",
        lambda: CharField(max_length=32, null=False, default="agent_canvas", help_text="agent_canvas|dataflow_canvas", index=True),
        "separates agent canvases from dataflow canvases",
    ),
    ColumnMigration(
        "user_canvas",
        "tags",
        lambda: CharField(max_length=512, null=False, default="", help_text="Comma-separated tags for organizing agents", index=True),
        "supports agent list categorization and filtering",
    ),
    ColumnMigration(
        "user_canvas_version",
        "release",
        lambda: BooleanField(null=False, help_text="is released", default=False, index=True),
        "tracks published status per agent canvas version",
    ),
    ColumnMigration(
        "canvas_template",
        "canvas_category",
        lambda: CharField(max_length=32, null=False, default="agent_canvas", help_text="agent_canvas|dataflow_canvas", index=True),
        "separates agent templates from dataflow templates",
    ),
    ColumnMigration(
        "canvas_template",
        "canvas_types",
        lambda: ListField(null=True, default=list, help_text="Canvas types"),
        "allows templates to advertise multiple agent capability types",
    ),
    ColumnMigration(
        "llm",
        "is_tools",
        lambda: BooleanField(null=False, help_text="support tools", default=False),
        "marks tool-capable models for agent node configuration",
    ),
    ColumnMigration(
        "mcp_server",
        "variables",
        lambda: JSONField(null=True, help_text="MCP Server variables", default=dict),
        "stores reusable MCP server variables for agent tools",
    ),
    ColumnMigration(
        "mcp_server",
        "headers",
        lambda: JSONField(null=True, help_text="MCP Server additional request headers", default=dict),
        "stores MCP request headers required by agent tools",
    ),
    ColumnMigration(
        "dialog",
        "memory_mode",
        lambda: CharField(max_length=32, null=False, default="kb_first", help_text="kb_first|memory_first|ignore_memory"),
        "configures how dialog-backed agent flows use memory",
    ),
    ColumnMigration(
        "tenant",
        "tenant_llm_id",
        lambda: IntegerField(null=True, help_text="id in tenant_llm", index=True),
        "lets agent flows bind to the local tenant chat model record",
    ),
    ColumnMigration(
        "dialog",
        "tenant_llm_id",
        lambda: IntegerField(null=True, help_text="id in tenant_llm", index=True),
        "lets dialog-backed agents use the local tenant chat model record",
    ),
]


TYPE_MIGRATIONS = [
    ColumnTypeMigration(
        "canvas_template",
        "title",
        lambda: JSONField(null=True, default=dict, help_text="Canvas title"),
        ("longtext", "text"),
        "stores localized agent template titles",
    ),
    ColumnTypeMigration(
        "canvas_template",
        "description",
        lambda: JSONField(null=True, default=dict, help_text="Canvas description"),
        ("longtext", "text"),
        "stores localized agent template descriptions",
    ),
]


def table_name(model: type[Any]) -> str:
    return model._meta.table_name


def table_exists(name: str) -> bool:
    try:
        return bool(DB.table_exists(name))
    except Exception as exc:
        logger.warning("Could not inspect table %s: %s", name, exc)
        return False


def column_exists(table: str, column: str) -> bool:
    try:
        return any(column_info.name == column for column_info in DB.get_columns(table))
    except Exception as exc:
        logger.warning("Could not inspect column %s.%s: %s", table, column, exc)
        return False


def column_data_type(table: str, column: str) -> str:
    try:
        for column_info in DB.get_columns(table):
            if column_info.name == column:
                return str(getattr(column_info, "data_type", "") or "").lower()
    except Exception as exc:
        logger.warning("Could not inspect type for %s.%s: %s", table, column, exc)
    return ""


def create_missing_tables(*, dry_run: bool) -> list[str]:
    missing_models = [model for model in AGENT_RELATED_MODELS if not table_exists(table_name(model))]
    if not missing_models:
        logger.info("Agent-related tables already exist")
        return []

    missing_names = [table_name(model) for model in missing_models]
    if dry_run:
        logger.info("DRY RUN: would create missing agent-related tables: %s", ", ".join(missing_names))
        return missing_names

    DB.create_tables(missing_models, safe=True)
    logger.info("Created missing agent-related tables: %s", ", ".join(missing_names))
    return missing_names


def apply_column_migrations(*, dry_run: bool) -> list[str]:
    migrator = db_models.DatabaseMigrator[settings.DATABASE_TYPE.upper()].value(DB)
    changed = []
    for item in COLUMN_MIGRATIONS:
        label = f"{item.table}.{item.column}"
        if not table_exists(item.table):
            logger.warning("Skipping %s because table %s does not exist", label, item.table)
            continue
        if column_exists(item.table, item.column):
            logger.info("Column exists: %s", label)
            continue
        if dry_run:
            logger.info("DRY RUN: would add column %s (%s)", label, item.reason)
            changed.append(label)
            continue

        migrate(migrator.add_column(item.table, item.column, item.field_factory()))
        logger.info("Added column %s (%s)", label, item.reason)
        changed.append(label)
    return changed


def apply_type_migrations(*, dry_run: bool) -> list[str]:
    migrator = db_models.DatabaseMigrator[settings.DATABASE_TYPE.upper()].value(DB)
    changed = []
    for item in TYPE_MIGRATIONS:
        label = f"{item.table}.{item.column}"
        if not table_exists(item.table):
            logger.warning("Skipping type migration for %s because table %s does not exist", label, item.table)
            continue
        if not column_exists(item.table, item.column):
            logger.warning("Skipping type migration for %s because the column does not exist", label)
            continue
        current_type = column_data_type(item.table, item.column)
        if current_type and current_type in item.target_data_types:
            logger.info("Column type already compatible: %s (%s)", label, current_type)
            continue
        if dry_run:
            logger.info("DRY RUN: would alter column type for %s from %s (%s)", label, current_type or "unknown", item.reason)
            changed.append(label)
            continue

        migrate(migrator.alter_column_type(item.table, item.column, item.field_factory()))
        logger.info("Altered column type for %s (%s)", label, item.reason)
        changed.append(label)
    return changed


def ensure_agent_workspaces(*, dry_run: bool) -> int:
    from api.db.services.workspace_file_service import WorkspaceFileService

    if not table_exists("user_canvas"):
        logger.warning("Skipping workspace creation because user_canvas does not exist")
        return 0

    query = db_models.UserCanvas.select(
        db_models.UserCanvas.id,
        db_models.UserCanvas.title,
        db_models.UserCanvas.user_id,
        db_models.UserCanvas.canvas_category,
    ).where(db_models.UserCanvas.canvas_category == "agent_canvas")

    count = query.count()
    if dry_run:
        logger.info("DRY RUN: would ensure managed workspaces for %s existing agents", count)
        return count

    for canvas in query:
        WorkspaceFileService.ensure_agent_workspace(
            canvas.id,
            title=canvas.title or "",
            tenant_id=canvas.user_id or "",
        )
    logger.info("Ensured managed workspaces for %s existing agents", count)
    return count


def run_migration(
    *,
    dry_run: bool,
    create_tables: bool,
    include_type_changes: bool,
    include_workspaces: bool,
) -> None:
    logger.info("Agent platform migration started; database_type=%s dry_run=%s", settings.DATABASE_TYPE, dry_run)
    with DB.connection_context():
        created_tables = create_missing_tables(dry_run=dry_run) if create_tables else []
        changed_columns = apply_column_migrations(dry_run=dry_run)
        changed_types = apply_type_migrations(dry_run=dry_run) if include_type_changes else []
        workspace_count = ensure_agent_workspaces(dry_run=dry_run) if include_workspaces else 0

    logger.info(
        "Agent platform migration finished; tables=%s columns=%s type_changes=%s workspaces=%s",
        len(created_tables),
        len(changed_columns),
        len(changed_types),
        workspace_count,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply current agent-platform database migrations.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and print changes without modifying the database.")
    parser.add_argument("--skip-create-tables", action="store_true", help="Do not create missing agent-related tables.")
    parser.add_argument("--skip-type-changes", action="store_true", help="Do not alter existing column types.")
    parser.add_argument(
        "--ensure-workspaces",
        action="store_true",
        help="Also create managed filesystem workspaces for existing agent canvases.",
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level, for example INFO or DEBUG.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )
    run_migration(
        dry_run=args.dry_run,
        create_tables=not args.skip_create_tables,
        include_type_changes=not args.skip_type_changes,
        include_workspaces=args.ensure_workspaces,
    )


if __name__ == "__main__":
    main()
