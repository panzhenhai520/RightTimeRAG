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

import datetime
import json
import math
import re
from decimal import Decimal
from typing import Any


READONLY_SQL_STARTERS = {"select", "with", "show", "describe", "desc", "explain"}
FORBIDDEN_SQL_KEYWORDS = {
    "alter",
    "analyze",
    "begin",
    "call",
    "commit",
    "copy",
    "create",
    "delete",
    "drop",
    "exec",
    "execute",
    "grant",
    "insert",
    "into",
    "load",
    "lock",
    "merge",
    "optimize",
    "repair",
    "replace",
    "reset",
    "revoke",
    "rollback",
    "set",
    "truncate",
    "unlock",
    "update",
    "use",
    "vacuum",
}
FORBIDDEN_SQL_FUNCTIONS = {
    "benchmark",
    "load_file",
    "pg_sleep",
    "sleep",
}
FORBIDDEN_SQL_TOKENS = {
    "dumpfile",
    "outfile",
}


SQL_VARIABLE_PATTERN = re.compile(
    r"\{([a-zA-Z:0-9]+@[A-Za-z0-9_.-]+|sys\.[A-Za-z0-9_.]+|env\.[A-Za-z0-9_.]+)\}"
)


def strip_sql_comments(sql: str) -> str:
    out = []
    quote = ""
    idx = 0
    while idx < len(sql):
        ch = sql[idx]
        nxt = sql[idx + 1] if idx + 1 < len(sql) else ""
        if quote:
            out.append(ch)
            if ch == quote:
                if nxt == quote:
                    out.append(nxt)
                    idx += 2
                    continue
                quote = ""
            elif ch == "\\" and nxt:
                out.append(nxt)
                idx += 2
                continue
            idx += 1
            continue

        if ch in {"'", '"', "`"}:
            quote = ch
            out.append(ch)
            idx += 1
            continue
        if ch == "-" and nxt == "-":
            idx += 2
            while idx < len(sql) and sql[idx] not in {"\n", "\r"}:
                idx += 1
            out.append(" ")
            continue
        if ch == "#":
            idx += 1
            while idx < len(sql) and sql[idx] not in {"\n", "\r"}:
                idx += 1
            out.append(" ")
            continue
        if ch == "/" and nxt == "*":
            idx += 2
            while idx + 1 < len(sql) and not (sql[idx] == "*" and sql[idx + 1] == "/"):
                idx += 1
            idx = min(idx + 2, len(sql))
            out.append(" ")
            continue
        out.append(ch)
        idx += 1
    return "".join(out)


def mask_sql_literals(sql: str) -> str:
    chars = list(sql)
    quote = ""
    escaped = False
    idx = 0
    while idx < len(chars):
        ch = chars[idx]
        if not quote:
            if ch in {"'", '"', "`"}:
                quote = ch
            idx += 1
            continue

        if escaped:
            chars[idx] = " "
            escaped = False
            idx += 1
            continue
        if ch == "\\":
            chars[idx] = " "
            escaped = True
            idx += 1
            continue
        if ch == quote:
            if idx + 1 < len(chars) and chars[idx + 1] == quote:
                chars[idx] = " "
                chars[idx + 1] = " "
                idx += 2
                continue
            quote = ""
            idx += 1
            continue
        chars[idx] = " "
        idx += 1
    return "".join(chars)


def split_sql_statements(sql: str) -> list[str]:
    statements = []
    current = []
    quote = ""
    escaped = False
    idx = 0
    while idx < len(sql):
        ch = sql[idx]
        nxt = sql[idx + 1] if idx + 1 < len(sql) else ""
        current.append(ch)
        if not quote:
            if ch in {"'", '"', "`"}:
                quote = ch
            elif ch == ";":
                statements.append("".join(current[:-1]).strip())
                current = []
            idx += 1
            continue

        if escaped:
            escaped = False
            idx += 1
            continue
        if ch == "\\":
            escaped = True
            idx += 1
            continue
        if ch == quote:
            if nxt == quote:
                current.append(nxt)
                idx += 2
                continue
            quote = ""
        idx += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return [statement for statement in statements if statement]


def sql_string_body(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        value = value.isoformat()
    elif isinstance(value, (dict, list, tuple, set)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value).replace("\\", "\\\\").replace("'", "''")


def format_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return "NULL"
        if isinstance(value, int):
            return str(value)
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return f"'{sql_string_body(value)}'"
    if isinstance(value, (list, tuple, set)):
        if not value:
            return "NULL"
        return ", ".join(format_sql_literal(item) for item in value)
    if isinstance(value, dict):
        return f"'{sql_string_body(value)}'"
    return f"'{sql_string_body(value)}'"


def is_inside_sql_string(sql: str, position: int) -> bool:
    quote = ""
    escaped = False
    idx = 0
    while idx < min(position, len(sql)):
        ch = sql[idx]
        nxt = sql[idx + 1] if idx + 1 < len(sql) else ""
        if not quote:
            if ch in {"'", '"'}:
                quote = ch
            idx += 1
            continue
        if escaped:
            escaped = False
            idx += 1
            continue
        if ch == "\\":
            escaped = True
            idx += 1
            continue
        if ch == quote:
            if nxt == quote:
                idx += 2
                continue
            quote = ""
        idx += 1
    return bool(quote)


def replace_sql_variables(sql: str, values: dict[str, Any]) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        value = values.get(key)
        if is_inside_sql_string(sql, match.start()):
            return sql_string_body(value)
        return format_sql_literal(value)

    return SQL_VARIABLE_PATTERN.sub(repl, sql)


def prepare_readonly_sqls(sql: str) -> list[str]:
    cleaned = strip_sql_comments(sql.replace("```", ""))
    statements = split_sql_statements(cleaned)
    if not statements:
        raise Exception("SQL for `ExeSQL` MUST not be empty.")
    if len(statements) > 1:
        raise Exception("For security reasons, ExeSQL supports only one read-only SQL statement at a time.")

    statement = re.sub(r"\[ID:[0-9]+\]", "", statements[0]).strip()
    starter = re.match(r"^\s*([a-zA-Z_]+)", statement)
    if not starter or starter.group(1).lower() not in READONLY_SQL_STARTERS:
        raise Exception("For security reasons, ExeSQL only supports read-only SQL statements.")

    masked = mask_sql_literals(statement)
    forbidden_tokens = sorted(FORBIDDEN_SQL_KEYWORDS | FORBIDDEN_SQL_TOKENS)
    forbidden = re.search(
        r"\b(" + "|".join(forbidden_tokens) + r")\b",
        masked,
        flags=re.IGNORECASE,
    )
    if forbidden:
        raise Exception(
            f"For security reasons, ExeSQL does not support `{forbidden.group(1).upper()}` statements."
        )
    forbidden_function = re.search(
        r"\b(" + "|".join(sorted(FORBIDDEN_SQL_FUNCTIONS)) + r")\s*\(",
        masked,
        flags=re.IGNORECASE,
    )
    if forbidden_function:
        raise Exception(
            f"For security reasons, ExeSQL does not support `{forbidden_function.group(1).upper()}` function calls."
        )
    return [statement]
