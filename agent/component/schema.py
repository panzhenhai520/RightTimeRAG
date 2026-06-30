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

import re
from copy import deepcopy
from typing import Any


SCHEMA_TYPE_ANY = "Any"
SCHEMA_TYPE_STRING = "String"
SCHEMA_TYPE_NUMBER = "Number"
SCHEMA_TYPE_BOOLEAN = "Boolean"
SCHEMA_TYPE_JSON = "JSON"
SCHEMA_TYPE_ARRAY = "Array"
SCHEMA_TYPE_FILE_ASSET = "FileAsset"
SCHEMA_TYPE_TEXT_DOCUMENT = "TextDocument"
SCHEMA_TYPE_TEXT_CHUNK = "TextChunk"
SCHEMA_TYPE_TABLE_DATA = "TableData"
SCHEMA_TYPE_SQL_RESULT = "SQLResult"
SCHEMA_TYPE_ARTIFACT = "Artifact"


_TYPE_ALIASES = {
    "any": SCHEMA_TYPE_ANY,
    "none": SCHEMA_TYPE_ANY,
    "nonetype": SCHEMA_TYPE_ANY,
    "str": SCHEMA_TYPE_STRING,
    "string": SCHEMA_TYPE_STRING,
    "text": SCHEMA_TYPE_STRING,
    "varchar": SCHEMA_TYPE_STRING,
    "int": SCHEMA_TYPE_NUMBER,
    "integer": SCHEMA_TYPE_NUMBER,
    "float": SCHEMA_TYPE_NUMBER,
    "double": SCHEMA_TYPE_NUMBER,
    "decimal": SCHEMA_TYPE_NUMBER,
    "number": SCHEMA_TYPE_NUMBER,
    "numeric": SCHEMA_TYPE_NUMBER,
    "bool": SCHEMA_TYPE_BOOLEAN,
    "boolean": SCHEMA_TYPE_BOOLEAN,
    "dict": SCHEMA_TYPE_JSON,
    "object": SCHEMA_TYPE_JSON,
    "json": SCHEMA_TYPE_JSON,
    "dataframe": SCHEMA_TYPE_JSON,
    "list": SCHEMA_TYPE_ARRAY,
    "array": SCHEMA_TYPE_ARRAY,
    "tuple": SCHEMA_TYPE_ARRAY,
    "file": SCHEMA_TYPE_FILE_ASSET,
    "upload": SCHEMA_TYPE_FILE_ASSET,
    "uploadedfile": SCHEMA_TYPE_FILE_ASSET,
    "fileasset": SCHEMA_TYPE_FILE_ASSET,
    "attachment": SCHEMA_TYPE_FILE_ASSET,
    "textdocument": SCHEMA_TYPE_TEXT_DOCUMENT,
    "document": SCHEMA_TYPE_TEXT_DOCUMENT,
    "textdoc": SCHEMA_TYPE_TEXT_DOCUMENT,
    "textchunk": SCHEMA_TYPE_TEXT_CHUNK,
    "chunk": SCHEMA_TYPE_TEXT_CHUNK,
    "tabledata": SCHEMA_TYPE_TABLE_DATA,
    "table": SCHEMA_TYPE_TABLE_DATA,
    "dataframe": SCHEMA_TYPE_TABLE_DATA,
    "sqlresult": SCHEMA_TYPE_SQL_RESULT,
    "sql_result": SCHEMA_TYPE_SQL_RESULT,
    "artifact": SCHEMA_TYPE_ARTIFACT,
}


def normalize_schema_type(type_name: Any) -> str:
    if not type_name:
        return SCHEMA_TYPE_ANY

    if isinstance(type_name, type):
        type_name = type_name.__name__

    raw = str(type_name).strip()
    match = re.match(r"<class '([^']+)'>", raw)
    if match:
        raw = match.group(1).rsplit(".", 1)[-1]

    compact = raw.replace(" ", "")
    lower = compact.lower()
    if lower.startswith("array<") and lower.endswith(">"):
        inner = normalize_schema_type(compact[6:-1])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"
    if lower.startswith("list[") and lower.endswith("]"):
        inner = normalize_schema_type(compact[5:-1])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"
    if lower.startswith("typing.list[") and lower.endswith("]"):
        inner = normalize_schema_type(compact[12:-1])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"
    if lower.endswith("[]") and len(compact) > 2:
        inner = normalize_schema_type(compact[:-2])
        return f"{SCHEMA_TYPE_ARRAY}<{inner}>"

    return _TYPE_ALIASES.get(lower, raw[:1].upper() + raw[1:] if raw else SCHEMA_TYPE_ANY)


def build_field_schema(name: str, spec: Any = None, default_required: bool = False) -> dict[str, Any]:
    field = {
        "name": str(name),
        "type": SCHEMA_TYPE_ANY,
        "required": default_required,
    }

    if isinstance(spec, dict):
        source = deepcopy(spec)
        field["type"] = normalize_schema_type(source.get("type") or source.get("schema_type"))
        if source.get("name"):
            field["label"] = source.get("name")
        if source.get("label"):
            field["label"] = source.get("label")
        if source.get("description"):
            field["description"] = source.get("description")
        if source.get("required") is not None:
            field["required"] = bool(source.get("required"))
        if source.get("items"):
            field["items"] = deepcopy(source.get("items"))
        if source.get("properties"):
            field["properties"] = deepcopy(source.get("properties"))
        if source.get("source"):
            field["source"] = source.get("source")
        return field

    field["type"] = normalize_schema_type(spec)
    return field


def build_schema_from_io(fields: Any, default_required: bool = False) -> dict[str, dict[str, Any]]:
    if not isinstance(fields, dict):
        return {}
    return {
        str(name): build_field_schema(str(name), spec, default_required=default_required)
        for name, spec in fields.items()
    }


def merge_schema(base: Any, overlay: Any) -> dict[str, Any]:
    if not isinstance(base, dict):
        base = {}
    if not isinstance(overlay, dict):
        return deepcopy(base)

    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_schema(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def build_runtime_capabilities(
    component_name: str,
    explicit: Any = None,
    inputs: dict[str, dict[str, Any]] | None = None,
    outputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, bool]:
    capabilities = {
        "streaming": False,
        "long_running": False,
        "produces_artifacts": False,
        "accepts_files": False,
        "uses_external_io": False,
        "supports_cancel": True,
    }

    name = (component_name or "").lower()
    if name in {"llm", "agent", "agentwithtools", "message"}:
        capabilities["streaming"] = True
        capabilities["long_running"] = True
    if name in {
        "retrieval",
        "browser",
        "codeexec",
        "exesql",
        "excelprocessor",
        "docgenerator",
        "invoke",
        "email",
    }:
        capabilities["long_running"] = True
    if name in {"codeexec", "excelprocessor", "docgenerator"}:
        capabilities["produces_artifacts"] = True
    if name in {"exesql", "retrieval", "browser", "invoke", "email"}:
        capabilities["uses_external_io"] = True

    for field in list((inputs or {}).values()) + list((outputs or {}).values()):
        field_type = normalize_schema_type(field.get("type") if isinstance(field, dict) else field)
        if field_type == SCHEMA_TYPE_FILE_ASSET or field_type.startswith(f"{SCHEMA_TYPE_ARRAY}<FileAsset"):
            capabilities["accepts_files"] = True
        if field_type == SCHEMA_TYPE_ARTIFACT or field_type.startswith(f"{SCHEMA_TYPE_ARRAY}<{SCHEMA_TYPE_ARTIFACT}"):
            capabilities["produces_artifacts"] = True

    if isinstance(explicit, dict):
        for key, value in explicit.items():
            if key in capabilities:
                capabilities[key] = bool(value)

    return capabilities
