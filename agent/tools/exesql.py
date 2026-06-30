#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
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
import contextlib
import json
import os
import re
from abc import ABC
import pandas as pd
import pymysql
import psycopg2
import pyodbc
from agent.tools.base import ToolParamBase, ToolBase, ToolMeta
from agent.sql_guard import prepare_readonly_sqls, replace_sql_variables
from common.connection_utils import timeout


class ExeSQLParam(ToolParamBase):
    """
    Define the ExeSQL component parameters.
    """

    def __init__(self):
        self.meta:ToolMeta = {
            "name": "execute_sql",
            "description": "This is a tool that can execute SQL.",
            "parameters": {
                "sql": {
                    "type": "string",
                    "description": "The SQL needs to be executed.",
                    "default": "{sys.query}",
                    "required": True
                }
            }
        }
        super().__init__()
        self.db_type = "mysql"
        self.database = ""
        self.username = ""
        self.host = ""
        self.port = 3306
        self.password = ""
        self.max_records = 1024
        self.outputs = {
            "formalized_content": {"value": "", "type": "string"},
            "json": {"value": [], "type": "Array<JSON>"},
            "sql_result": {"value": {}, "type": "SQLResult"},
            "row_count": {"value": 0, "type": "number"},
            "truncated": {"value": False, "type": "boolean"},
        }

    def check(self):
        self.check_valid_value(self.db_type, "Choose DB type", ['mysql', 'postgres', 'mariadb', 'mssql', 'IBM DB2', 'trino', 'oceanbase'])
        self.check_empty(self.database, "Database name")
        self.check_empty(self.username, "database username")
        self.check_empty(self.host, "IP Address")
        self.check_positive_integer(self.port, "IP Port")
        if self.db_type != "trino":
            self.check_empty(self.password, "Database password")
        self.check_positive_integer(self.max_records, "Maximum number of records")
        if self.database == "rag_flow":
            if self.host == "ragflow-mysql":
                raise ValueError("For the security reason, it does not support database named rag_flow.")
            if self.password == "infini_rag_flow":
                raise ValueError("For the security reason, it does not support database named rag_flow.")

    def get_input_form(self) -> dict[str, dict]:
        return {
            "sql": {
                "name": "SQL",
                "type": "line"
            }
        }


class ExeSQL(ToolBase, ABC):
    component_name = "ExeSQL"

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ExeSQL processing"):
            return

        def convert_decimals(obj):
            from decimal import Decimal
            import math
            if isinstance(obj, float):
                # Handle NaN and Infinity which are not valid JSON values
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            if isinstance(obj, Decimal):
                return float(obj)  # 或 str(obj)
            elif isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            return obj

        sql = kwargs.get("sql")
        if not sql:
            raise Exception("SQL for `ExeSQL` MUST not be empty.")

        if self.check_if_canceled("ExeSQL processing"):
            return

        vars = self.get_input_elements_from_text(sql)
        args = {}
        for k, o in vars.items():
            args[k] = o["value"]
            try:
                display_value = json.dumps(args[k], ensure_ascii=False)
            except Exception:
                display_value = str(args[k])
            self.set_input_value(k, display_value)
        sql = replace_sql_variables(sql, args)

        if self.check_if_canceled("ExeSQL processing"):
            return

        sqls = prepare_readonly_sqls(sql)

        def set_sql_outputs(statement_results, formalized_content):
            total_rows = sum(item.get("row_count", 0) for item in statement_results)
            truncated = any(item.get("truncated", False) for item in statement_results)
            sql_result = {
                "statements": statement_results,
                "rows": statement_results[0].get("rows", []) if len(statement_results) == 1 else [],
                "row_count": total_rows,
                "truncated": truncated,
                "max_records": self._param.max_records,
            }
            self.set_output("sql_result", sql_result)
            self.set_output("row_count", total_rows)
            self.set_output("truncated", truncated)
            self.set_output("json", [item.get("rows", []) for item in statement_results])
            self.set_output("formalized_content", "\n\n".join(formalized_content))
        if self._param.db_type in ["mysql", "mariadb"]:
            db = pymysql.connect(db=self._param.database, user=self._param.username, host=self._param.host,
                                 port=self._param.port, password=self._param.password)
        elif self._param.db_type == 'oceanbase':
            db = pymysql.connect(db=self._param.database, user=self._param.username, host=self._param.host,
                                 port=self._param.port, password=self._param.password, charset='utf8mb4')
        elif self._param.db_type == 'postgres':
            db = psycopg2.connect(dbname=self._param.database, user=self._param.username, host=self._param.host,
                                  port=self._param.port, password=self._param.password)
        elif self._param.db_type == 'mssql':
            conn_str = (
                    r'DRIVER={ODBC Driver 17 for SQL Server};'
                    r'SERVER=' + self._param.host + ',' + str(self._param.port) + ';'
                    r'DATABASE=' + self._param.database + ';'
                    r'UID=' + self._param.username + ';'
                    r'PWD=' + self._param.password
            )
            db = pyodbc.connect(conn_str)
        elif self._param.db_type == 'trino':
            try:
                import trino
                from trino.auth import BasicAuthentication
            except Exception:
                raise Exception("Missing dependency 'trino'. Please install: pip install trino")

            def _parse_catalog_schema(db: str):
                if not db:
                    return None, None
                if "." in db:
                    c, s = db.split(".", 1)
                elif "/" in db:
                    c, s = db.split("/", 1)
                else:
                    c, s = db, "default"
                return c, s

            catalog, schema = _parse_catalog_schema(self._param.database)
            if not catalog:
                raise Exception("For Trino, `database` must be 'catalog.schema' or at least 'catalog'.")

            http_scheme = "https" if os.environ.get("TRINO_USE_TLS", "0") == "1" else "http"
            auth = None
            if http_scheme == "https" and self._param.password:
                auth = BasicAuthentication(self._param.username, self._param.password)

            try:
                db = trino.dbapi.connect(
                    host=self._param.host,
                    port=int(self._param.port or 8080),
                    user=self._param.username or "ragflow",
                    catalog=catalog,
                    schema=schema or "default",
                    http_scheme=http_scheme,
                    auth=auth
                )
            except Exception as e:
                raise Exception("Database Connection Failed! \n" + str(e))
        elif self._param.db_type == 'IBM DB2':
            import ibm_db
            conn_str = (
                f"DATABASE={self._param.database};"
                f"HOSTNAME={self._param.host};"
                f"PORT={self._param.port};"
                f"PROTOCOL=TCPIP;"
                f"UID={self._param.username};"
                f"PWD={self._param.password};"
            )
            try:
                conn = ibm_db.connect(conn_str, "", "")
            except Exception as e:
                raise Exception("Database Connection Failed! \n" + str(e))

            try:
                statement_results = []
                formalized_content = []
                for single_sql in sqls:
                    if self.check_if_canceled("ExeSQL processing"):
                        return

                    single_sql = single_sql.strip()
                    if not single_sql:
                        continue

                    stmt = ibm_db.exec_immediate(conn, single_sql)
                    rows = []
                    truncated = False
                    row = ibm_db.fetch_assoc(stmt)
                    while row and len(rows) <= self._param.max_records:
                        if self.check_if_canceled("ExeSQL processing"):
                            return
                        if len(rows) >= self._param.max_records:
                            truncated = True
                            break
                        rows.append(row)
                        row = ibm_db.fetch_assoc(stmt)

                    if not rows:
                        statement_results.append(
                            {"sql": single_sql, "rows": [], "row_count": 0, "truncated": False}
                        )
                        continue

                    df = pd.DataFrame(rows)
                    for col in df.columns:
                        if pd.api.types.is_datetime64_any_dtype(df[col]):
                            df[col] = df[col].dt.strftime("%Y-%m-%d")

                    df = df.where(pd.notnull(df), None)

                    rows = convert_decimals(df.to_dict(orient="records"))
                    statement_results.append(
                        {
                            "sql": single_sql,
                            "rows": rows,
                            "row_count": len(rows),
                            "truncated": truncated,
                        }
                    )
                    formalized_content.append(df.to_markdown(index=False, floatfmt=".6f"))
            finally:
                with contextlib.suppress(Exception):
                    ibm_db.close(conn)

            set_sql_outputs(statement_results, formalized_content)
            return self.output("formalized_content")
        try:
            cursor = db.cursor()
        except Exception as e:
            with contextlib.suppress(Exception):
                db.close()
            raise Exception("Database Connection Failed! \n" + str(e))

        try:
            statement_results = []
            formalized_content = []
            for single_sql in sqls:
                if self.check_if_canceled("ExeSQL processing"):
                    return

                single_sql = single_sql.strip()
                if not single_sql:
                    continue
                cursor.execute(single_sql)
                if self._param.db_type == 'mssql':
                    fetched_rows = cursor.fetchmany(self._param.max_records + 1)
                    truncated = len(fetched_rows) > self._param.max_records
                    fetched_rows = fetched_rows[: self._param.max_records]
                    single_res = pd.DataFrame.from_records(
                        fetched_rows,
                        columns=[desc[0] for desc in cursor.description],
                    )
                else:
                    fetched_rows = cursor.fetchmany(self._param.max_records + 1)
                    truncated = len(fetched_rows) > self._param.max_records
                    fetched_rows = fetched_rows[: self._param.max_records]
                    single_res = pd.DataFrame([i for i in fetched_rows])
                    if cursor.description:
                        single_res.columns = [i[0] for i in cursor.description]

                if single_res.empty:
                    statement_results.append(
                        {"sql": single_sql, "rows": [], "row_count": 0, "truncated": False}
                    )
                    continue

                for col in single_res.columns:
                    if pd.api.types.is_datetime64_any_dtype(single_res[col]):
                        single_res[col] = single_res[col].dt.strftime('%Y-%m-%d')

                single_res = single_res.where(pd.notnull(single_res), None)

                rows = convert_decimals(single_res.to_dict(orient='records'))
                statement_results.append(
                    {
                        "sql": single_sql,
                        "rows": rows,
                        "row_count": len(rows),
                        "truncated": truncated,
                    }
                )
                formalized_content.append(single_res.to_markdown(index=False, floatfmt=".6f"))
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            with contextlib.suppress(Exception):
                db.close()

        set_sql_outputs(statement_results, formalized_content)
        return self.output("formalized_content")

    def thoughts(self) -> str:
        return "Query sent—waiting for the data."
