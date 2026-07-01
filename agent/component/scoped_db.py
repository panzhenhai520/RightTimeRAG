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

import json
import os
import re
import sqlite3
from abc import ABC
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.utils.api_utils import timeout


SCOPED_DB_ROOT = os.environ.get("AGENT_SCOPED_DB_ROOT", "/tmp/ragflow_agent_scoped_db")

SAFE_TABLE_TEMPLATES = {
    "teaching_activity": {
        "columns": {
            "id": "TEXT PRIMARY KEY",
            "tenant_id": "TEXT NOT NULL",
            "agent_id": "TEXT NOT NULL",
            "activity_id": "TEXT",
            "student_id": "TEXT",
            "lesson_text": "TEXT",
            "summary": "TEXT",
            "score": "REAL",
            "payload_json": "TEXT",
            "created_at": "TEXT NOT NULL",
        },
        "required": ["id", "tenant_id", "agent_id", "created_at"],
    },
    "student_score": {
        "columns": {
            "id": "TEXT PRIMARY KEY",
            "tenant_id": "TEXT NOT NULL",
            "agent_id": "TEXT NOT NULL",
            "student_id": "TEXT",
            "activity_id": "TEXT",
            "score": "REAL",
            "self_score": "REAL",
            "external_score": "REAL",
            "rubric_json": "TEXT",
            "payload_json": "TEXT",
            "created_at": "TEXT NOT NULL",
        },
        "required": ["id", "tenant_id", "agent_id", "created_at"],
    },
}


class ScopedDB:
    @staticmethod
    def safe_identifier(value: Any, fallback: str = "default") -> str:
        text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
        if not text:
            text = fallback
        if not re.match(r"^[a-zA-Z_]", text):
            text = f"_{text}"
        return text[:64]

    @classmethod
    def safe_table_name(cls, agent_id: str, template: str) -> str:
        if template not in SAFE_TABLE_TEMPLATES:
            raise ValueError(f"Unsupported table template: {template}")
        return f"agent_{cls.safe_identifier(agent_id)}_{template}"

    @staticmethod
    def default_db_path(tenant_id: str) -> str:
        os.makedirs(SCOPED_DB_ROOT, exist_ok=True)
        safe_tenant = ScopedDB.safe_identifier(tenant_id)
        return os.path.join(SCOPED_DB_ROOT, f"{safe_tenant}.sqlite3")

    @staticmethod
    def ensure_safe_db_path(path: str) -> str:
        root = os.path.abspath(SCOPED_DB_ROOT)
        path = os.path.abspath(path)
        if path != root and not path.startswith(root + os.sep):
            raise ValueError("Scoped database path must stay inside AGENT_SCOPED_DB_ROOT")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    @staticmethod
    def parse_json_like(value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                return json.loads(text)
            except Exception:
                return {}
        return value

    @classmethod
    def connector_ref(cls, tenant_id: str, agent_id: str, db_path: str = "") -> dict[str, Any]:
        path = db_path or cls.default_db_path(tenant_id)
        return {
            "dialect": "sqlite",
            "tenant_id": str(tenant_id or ""),
            "agent_id": cls.safe_identifier(agent_id),
            "db_path": cls.ensure_safe_db_path(path),
            "namespace": f"agent_{cls.safe_identifier(agent_id)}_",
        }

    @classmethod
    def assert_tenant(cls, db_ref: dict[str, Any], tenant_id: str) -> None:
        if str(db_ref.get("tenant_id") or "") != str(tenant_id or ""):
            raise PermissionError("Scoped database tenant mismatch")

    @classmethod
    def ensure_table(cls, db_ref: dict[str, Any], template: str) -> dict[str, Any]:
        table_name = cls.safe_table_name(db_ref.get("agent_id") or "default", template)
        columns = SAFE_TABLE_TEMPLATES[template]["columns"]
        column_sql = ", ".join(f"{name} {definition}" for name, definition in columns.items())
        with closing(sqlite3.connect(db_ref["db_path"])) as conn:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({column_sql})")
            conn.commit()
        return {"db_ref": db_ref, "template": template, "table_name": table_name, "columns": list(columns.keys())}

    @staticmethod
    def _serialize_value(key: str, value: Any) -> Any:
        if key.endswith("_json") and not isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        return value

    @classmethod
    def normalize_record(cls, table_ref: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            record = {}
        template = table_ref["template"]
        allowed = SAFE_TABLE_TEMPLATES[template]["columns"]
        db_ref = table_ref["db_ref"]
        now = datetime.now(timezone.utc).isoformat()
        base = {
            "id": str(record.get("id") or f"{template}_{int(datetime.now(timezone.utc).timestamp() * 1000000)}"),
            "tenant_id": db_ref["tenant_id"],
            "agent_id": db_ref["agent_id"],
            "created_at": record.get("created_at") or now,
        }
        normalized = {**base}
        for key in allowed:
            if key in record:
                normalized[key] = cls._serialize_value(key, record[key])
        if record and "payload_json" in allowed and "payload_json" not in normalized:
            normalized["payload_json"] = json.dumps(record, ensure_ascii=False)
        return {key: normalized.get(key) for key in allowed if key in normalized}

    @classmethod
    def insert_record(cls, table_ref: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        row = cls.normalize_record(table_ref, record)
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table_ref['table_name']} ({', '.join(columns)}) VALUES ({placeholders})"
        with closing(sqlite3.connect(table_ref["db_ref"]["db_path"])) as conn:
            conn.execute(sql, [row[column] for column in columns])
            conn.commit()
        return row

    @classmethod
    def update_records(cls, table_ref: dict[str, Any], values: dict[str, Any], filters: dict[str, Any]) -> int:
        template = table_ref["template"]
        allowed = SAFE_TABLE_TEMPLATES[template]["columns"]
        values = {key: cls._serialize_value(key, value) for key, value in (values or {}).items() if key in allowed and key not in {"tenant_id", "agent_id"}}
        filters = {key: value for key, value in (filters or {}).items() if key in allowed}
        if not values or not filters:
            return 0
        set_sql = ", ".join(f"{key} = ?" for key in values)
        where_sql = " AND ".join(f"{key} = ?" for key in filters)
        sql = f"UPDATE {table_ref['table_name']} SET {set_sql} WHERE {where_sql}"
        with closing(sqlite3.connect(table_ref["db_ref"]["db_path"])) as conn:
            cursor = conn.execute(sql, [*values.values(), *filters.values()])
            conn.commit()
            return int(cursor.rowcount or 0)

    @classmethod
    def query_records(cls, table_ref: dict[str, Any], filters: dict[str, Any] | None = None, limit: int = 100) -> dict[str, Any]:
        template = table_ref["template"]
        allowed = SAFE_TABLE_TEMPLATES[template]["columns"]
        filters = {key: value for key, value in (filters or {}).items() if key in allowed}
        where_sql = ""
        args = []
        if filters:
            where_sql = " WHERE " + " AND ".join(f"{key} = ?" for key in filters)
            args = list(filters.values())
        limit = max(1, min(int(limit or 100), 1000))
        sql = f"SELECT * FROM {table_ref['table_name']}{where_sql} LIMIT ?"
        with closing(sqlite3.connect(table_ref["db_ref"]["db_path"])) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(sql, [*args, limit]).fetchall()]
        return {
            "statements": [{"sql": sql, "rows": rows, "row_count": len(rows), "truncated": len(rows) >= limit}],
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) >= limit,
            "max_records": limit,
        }


class ScopedDBConnectorParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.agent_id = ""
        self.db_path = ""
        self.outputs = {"db_ref": {"value": {}, "type": "JSON"}}

    def check(self):
        return True


class ScopedDBConnector(ComponentBase, ABC):
    component_name = "ScopedDBConnector"

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        tenant_id = self._canvas.get_tenant_id()
        agent_id = self._param.agent_id or getattr(self._canvas, "_id", None) or "default"
        self.set_output("db_ref", ScopedDB.connector_ref(tenant_id, agent_id, self._param.db_path))


class SafeTableEnsureParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.db_ref = ""
        self.table_template = "teaching_activity"
        self.outputs = {
            "table_ref": {"value": {}, "type": "JSON"},
            "table_name": {"value": "", "type": "string"},
        }

    def check(self):
        self.check_valid_value(self.table_template, "[SafeTableEnsure] Table template", list(SAFE_TABLE_TEMPLATES.keys()))


class SafeTableEnsure(ComponentBase, ABC):
    component_name = "SafeTableEnsure"

    def _resolve_db_ref(self):
        value = self._param.db_ref
        if isinstance(value, str) and self._canvas.is_reff(value):
            value = self._canvas.get_variable_value(value)
        value = ScopedDB.parse_json_like(value)
        if not isinstance(value, dict):
            raise ValueError("SafeTableEnsure requires a scoped db_ref")
        ScopedDB.assert_tenant(value, self._canvas.get_tenant_id())
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        table_ref = ScopedDB.ensure_table(self._resolve_db_ref(), self._param.table_template)
        self.set_output("table_ref", table_ref)
        self.set_output("table_name", table_ref["table_name"])


class SafeRecordInsertParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.table_ref = ""
        self.record = {}
        self.outputs = {
            "row": {"value": {}, "type": "JSON"},
            "row_count": {"value": 0, "type": "number"},
        }

    def check(self):
        return True


class SafeRecordInsert(ComponentBase, ABC):
    component_name = "SafeRecordInsert"

    def _resolve_table_ref(self):
        value = self._param.table_ref
        if isinstance(value, str) and self._canvas.is_reff(value):
            value = self._canvas.get_variable_value(value)
        value = ScopedDB.parse_json_like(value)
        if not isinstance(value, dict) or not value.get("db_ref"):
            raise ValueError("SafeRecordInsert requires a scoped table_ref")
        ScopedDB.assert_tenant(value["db_ref"], self._canvas.get_tenant_id())
        return value

    def _resolve_record(self):
        value = self._param.record
        if isinstance(value, str) and self._canvas.is_reff(value):
            value = self._canvas.get_variable_value(value)
        value = ScopedDB.parse_json_like(value)
        return value if isinstance(value, dict) else {}

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        row = ScopedDB.insert_record(self._resolve_table_ref(), self._resolve_record())
        self.set_output("row", row)
        self.set_output("row_count", 1)


class SafeRecordUpdateParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.table_ref = ""
        self.values = {}
        self.filters = {}
        self.outputs = {"row_count": {"value": 0, "type": "number"}}

    def check(self):
        return True


class SafeRecordUpdate(SafeRecordInsert, ABC):
    component_name = "SafeRecordUpdate"

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        values = ScopedDB.parse_json_like(self._param.values)
        filters = ScopedDB.parse_json_like(self._param.filters)
        row_count = ScopedDB.update_records(
            self._resolve_table_ref(),
            values if isinstance(values, dict) else {},
            filters if isinstance(filters, dict) else {},
        )
        self.set_output("row_count", row_count)


class SafeRecordQueryParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.table_ref = ""
        self.filters = {}
        self.limit = 100
        self.outputs = {
            "sql_result": {"value": {}, "type": "SQLResult"},
            "data": {"value": {}, "type": "TableData"},
            "row_count": {"value": 0, "type": "number"},
        }

    def check(self):
        self.check_positive_integer(self.limit, "[SafeRecordQuery] Limit")


class SafeRecordQuery(SafeRecordInsert, ABC):
    component_name = "SafeRecordQuery"

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        filters = ScopedDB.parse_json_like(self._param.filters)
        result = ScopedDB.query_records(
            self._resolve_table_ref(),
            filters if isinstance(filters, dict) else {},
            self._param.limit,
        )
        self.set_output("sql_result", result)
        self.set_output("data", {"rows": result["rows"]})
        self.set_output("row_count", result["row_count"])
