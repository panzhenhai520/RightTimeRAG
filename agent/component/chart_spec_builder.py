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
from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.utils.api_utils import timeout


class ChartSpecBuilderParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.chart_type = "line"
        self.title = ""
        self.data = ""
        self.x_field = ""
        self.y_field = ""
        self.series_field = ""
        self.dimensions = []
        self.outputs = {
            "chart_spec": {"value": {}, "type": "ChartSpec"},
            "charts": {"value": [], "type": "Array<ChartSpec>"},
            "summary": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "data": {"type": "Any", "required": True},
        }

    def check(self):
        self.check_valid_value(
            self.chart_type,
            "[ChartSpecBuilder] Chart type",
            ["line", "bar", "radar"],
        )


class ChartSpecBuilder(ComponentBase, ABC):
    component_name = "ChartSpecBuilder"

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return 0.0

    @classmethod
    def records_from_data(cls, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, str):
            text = data.strip()
            if not text:
                return []
            try:
                data = json.loads(text)
            except Exception:
                return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if all(isinstance(value, list) for value in data.values()):
                records = []
                for sheet_name, rows in data.items():
                    for row in rows:
                        if isinstance(row, dict):
                            records.append({"_series": sheet_name, **row})
                return records
            return [data]
        return []

    @classmethod
    def build_spec(
        cls,
        chart_type: str,
        records: list[dict[str, Any]],
        title: str = "",
        x_field: str = "",
        y_field: str = "",
        series_field: str = "",
        dimensions: list[str] | None = None,
    ) -> dict[str, Any]:
        chart_type = chart_type or "line"
        dimensions = [str(item) for item in (dimensions or []) if str(item).strip()]
        if chart_type in {"line", "bar"}:
            points = [
                {
                    "x": row.get(x_field) if x_field else idx + 1,
                    "y": cls._number(row.get(y_field)) if y_field else 0.0,
                    "series": row.get(series_field) if series_field else row.get("_series"),
                }
                for idx, row in enumerate(records)
            ]
            return {
                "schema_version": 1,
                "type": chart_type,
                "title": title,
                "encoding": {"x": x_field, "y": y_field, "series": series_field},
                "data": points,
            }

        series = []
        label_field = series_field or x_field
        for idx, row in enumerate(records):
            label = row.get(label_field) if label_field else f"record-{idx + 1}"
            series.append(
                {
                    "label": label,
                    "values": [
                        {"axis": dim, "value": cls._number(row.get(dim))}
                        for dim in dimensions
                    ],
                }
            )
        return {
            "schema_version": 1,
            "type": "radar",
            "title": title,
            "dimensions": dimensions,
            "series": series,
        }

    def _resolve_data(self, value: Any) -> Any:
        if isinstance(value, str) and value:
            try:
                if self._canvas.is_reff(value):
                    return self._canvas.get_variable_value(value)
                if "@" in value and "{" in value:
                    return self._canvas.get_value_with_variable(value)
            except Exception:
                return value
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ChartSpecBuilder processing"):
            return
        data = self._resolve_data(self._param.data or kwargs.get("data"))
        records = self.records_from_data(data)
        spec = self.build_spec(
            self._param.chart_type,
            records,
            title=self._param.title,
            x_field=self._param.x_field,
            y_field=self._param.y_field,
            series_field=self._param.series_field,
            dimensions=self._param.dimensions,
        )
        self.set_output("chart_spec", spec)
        self.set_output("charts", [spec])
        self.set_output("summary", f"Built {spec['type']} chart spec with {len(records)} record(s).")

    def thoughts(self) -> str:
        return "Building chart specification."
