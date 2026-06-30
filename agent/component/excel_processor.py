#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
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
ExcelProcessor Component

A component for reading, processing, and generating Excel files in RAGFlow agents.
Supports multiple Excel file inputs, data transformation, and Excel output generation.
"""

import logging
import os
from abc import ABC
from io import BytesIO

import pandas as pd

from agent.artifact_service import ArtifactService
from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.file_service import FileService
from api.utils.api_utils import timeout


class ExcelProcessorParam(ComponentParamBase):
    """
    Define the ExcelProcessor component parameters.
    """
    def __init__(self):
        super().__init__()
        # Input configuration
        self.input_files = []  # Variable references to uploaded files
        self.operation = "read"  # read, aggregate, calculate, merge, transform, output/export
        
        # Processing options
        self.sheet_selection = "all"  # all, first, or comma-separated sheet names
        self.merge_strategy = "concat"  # concat, join
        self.join_on = ""  # Column name for join operations
        
        # Transform options (for LLM-guided transformations)
        self.transform_instructions = ""
        self.transform_data = ""  # Variable reference to transformation data
        
        # Output options
        self.output_format = "xlsx"  # xlsx, csv
        self.output_filename = "output"

        # Aggregate options
        self.aggregate_column_keywords = ["合计", "总计", "金额合计", "total", "sum", "amount"]
        self.aggregate_coefficient = 1
        self.aggregate_result_name = "B"

        # Calculation options. This deterministic Number step keeps arithmetic
        # out of the LLM prompt when a flow only needs value * coefficient.
        self.calculation_value = ""
        self.calculation_coefficient = 1
        self.calculation_result_name = "B"
        
        # Component outputs
        self.outputs = {
            "data": {
                "type": "TableData",
                "value": {}
            },
            "summary": {
                "type": "str",
                "value": ""
            },
            "markdown": {
                "type": "str",
                "value": ""
            },
            "aggregate": {
                "type": "JSON",
                "value": {}
            },
            "result": {
                "type": "number",
                "value": 0
            },
            "downloads": {
                "type": "Array<Artifact>",
                "value": []
            },
            "attachment": {
                "type": "Artifact",
                "value": {}
            },
        }
    
    def check(self):
        self.check_valid_value(
            self.operation, 
            "[ExcelProcessor] Operation", 
            ["read", "merge", "transform", "output", "export", "aggregate", "calculate"]
        )
        self.check_valid_value(
            self.output_format,
            "[ExcelProcessor] Output format",
            ["xlsx", "csv"]
        )
        return True


class ExcelProcessor(ComponentBase, ABC):
    """
    Excel processing component for RAGFlow agents.
    
    Operations:
    - read: Parse Excel files into structured data
    - merge: Combine multiple Excel files
    - transform: Apply data transformations based on instructions
    - output: Generate Excel file output
    """
    component_name = "ExcelProcessor"
    _broad_aggregate_keywords = {"amount", "金额"}

    def get_input_form(self) -> dict[str, dict]:
        """Define input form for the component."""
        res = {}
        for ref in (self._param.input_files or []):
            for k, o in self.get_input_elements_from_text(ref).items():
                res[k] = {"name": o.get("name", ""), "type": "file"}
        if self._param.transform_data:
            for k, o in self.get_input_elements_from_text(self._param.transform_data).items():
                res[k] = {"name": o.get("name", ""), "type": "object"}
        if isinstance(self._param.aggregate_coefficient, str):
            for k, o in self.get_input_elements_from_text(self._param.aggregate_coefficient).items():
                res[k] = {"name": o.get("name", ""), "type": "number"}
        if self._param.calculation_value:
            for k, o in self.get_input_elements_from_text(self._param.calculation_value).items():
                res[k] = {"name": o.get("name", ""), "type": "number"}
        if isinstance(self._param.calculation_coefficient, str):
            for k, o in self.get_input_elements_from_text(self._param.calculation_coefficient).items():
                res[k] = {"name": o.get("name", ""), "type": "number"}
        return res

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10*60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ExcelProcessor processing"):
            return

        operation = self._param.operation.lower()
        
        if operation == "read":
            self._read_excels()
        elif operation == "merge":
            self._merge_excels()
        elif operation == "transform":
            self._transform_data()
        elif operation in {"output", "export"}:
            self._output_excel()
        elif operation == "aggregate":
            self._aggregate_total_column()
        elif operation == "calculate":
            self._calculate_number()
        else:
            self.set_output("summary", f"Unknown operation: {operation}")

    def _get_file_content(self, file_ref: str) -> tuple[bytes, str]:
        """
        Get file content from a variable reference.
        Returns (content_bytes, filename).
        """
        value = self._canvas.get_variable_value(file_ref) if isinstance(file_ref, str) else file_ref
        return self._get_file_content_from_value(value)

    def _get_file_content_from_value(self, value) -> tuple[bytes, str]:
        if value is None:
            return None, None
            
        # Handle different value formats
        if isinstance(value, dict):
            # File reference from Begin/UserFillUp component
            file_id = value.get("id") or value.get("file_id")
            created_by = value.get("created_by") or self._canvas.get_tenant_id()
            filename = value.get("name") or value.get("filename", "unknown.xlsx")
            if file_id:
                content = FileService.get_blob(created_by, file_id)
                return content, filename
        elif isinstance(value, list) and len(value) > 0:
            # List of file references - return first readable file
            for item in value:
                content, filename = self._get_file_content_from_value(item)
                if content is not None:
                    return content, filename
        elif isinstance(value, str):
            # Could be base64 encoded or a path
            if value.startswith("data:"):
                import base64
                # Extract base64 content
                _, encoded = value.split(",", 1)
                return base64.b64decode(encoded), "uploaded.xlsx"
                
        return None, None

    def _parse_excel_to_dataframes(self, content: bytes, filename: str) -> dict[str, pd.DataFrame]:
        """Parse Excel content into a dictionary of DataFrames (one per sheet)."""
        try:
            excel_file = BytesIO(content)
            
            if filename.lower().endswith(".csv"):
                df = pd.read_csv(excel_file)
                return {"Sheet1": df}
            else:
                # Read all sheets
                xlsx = pd.ExcelFile(excel_file, engine='openpyxl')
                sheet_selection = self._param.sheet_selection
                
                if sheet_selection == "all":
                    sheets_to_read = xlsx.sheet_names
                elif sheet_selection == "first":
                    sheets_to_read = [xlsx.sheet_names[0]] if xlsx.sheet_names else []
                else:
                    # Comma-separated sheet names
                    requested = [s.strip() for s in sheet_selection.split(",")]
                    sheets_to_read = [s for s in requested if s in xlsx.sheet_names]
                
                dfs = {}
                for sheet in sheets_to_read:
                    dfs[sheet] = pd.read_excel(xlsx, sheet_name=sheet)
                return dfs
                
        except Exception as e:
            logging.error(f"Error parsing Excel file {filename}: {e}")
            return {}

    def _resolve_number(self, value, default: float = 1.0) -> float:
        try:
            if isinstance(value, str) and self._canvas.is_reff(value):
                value = self._canvas.get_variable_value(value)
            elif isinstance(value, str):
                refs = self.get_input_elements_from_text(value)
                if len(refs) == 1 and value.strip().strip("{}").strip() in refs:
                    value = next(iter(refs.values())).get("value")
            return float(str(value).replace(",", "").strip())
        except Exception:
            return default

    @staticmethod
    def _normalize_column_name(column) -> str:
        return str(column or "").strip().lower().replace(" ", "")

    def _match_aggregate_columns(self, columns) -> list:
        keywords = self._param.aggregate_column_keywords or []
        if isinstance(keywords, str):
            keywords = [item.strip() for item in keywords.split(",") if item.strip()]
        normalized_keywords = [self._normalize_column_name(keyword) for keyword in keywords]
        strong_keywords = [
            keyword for keyword in normalized_keywords if keyword not in self._broad_aggregate_keywords
        ]
        broad_keywords = [
            keyword for keyword in normalized_keywords if keyword in self._broad_aggregate_keywords
        ]

        strong_matches = []
        broad_matches = []
        for column in columns:
            normalized_column = self._normalize_column_name(column)
            if any(keyword and keyword in normalized_column for keyword in strong_keywords):
                strong_matches.append(column)
            elif any(keyword and keyword in normalized_column for keyword in broad_keywords):
                broad_matches.append(column)
        return strong_matches or broad_matches

    @staticmethod
    def _sum_numeric_series(series) -> float:
        values = (
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(r"[^\d\.\-]", "", regex=True)
        )
        return float(pd.to_numeric(values, errors="coerce").fillna(0).sum())

    def _aggregate_total_column(self):
        details = []
        total = 0.0
        all_columns = {}

        for file_ref in (self._param.input_files or []):
            if self.check_if_canceled("ExcelProcessor aggregating"):
                return

            value = self._canvas.get_variable_value(file_ref)
            self.set_input_value(file_ref, str(value)[:200] if value else "")

            if value is None:
                continue

            content, filename = self._get_file_content(file_ref)
            if content is None:
                continue

            dfs = self._parse_excel_to_dataframes(content, filename)
            for sheet_name, df in dfs.items():
                sheet_key = f"{filename}:{sheet_name}"
                columns = df.columns.tolist()
                all_columns[sheet_key] = [str(column) for column in columns]
                matched_columns = self._match_aggregate_columns(columns)
                for column in matched_columns:
                    column_sum = self._sum_numeric_series(df[column])
                    total += column_sum
                    details.append(
                        {
                            "file": filename,
                            "sheet": sheet_name,
                            "column": str(column),
                            "rows": len(df),
                            "sum": column_sum,
                        }
                    )

        coefficient = self._resolve_number(self._param.aggregate_coefficient, 1.0)
        result = total * coefficient
        aggregate = {
            "result_name": self._param.aggregate_result_name or "B",
            "total": total,
            "coefficient": coefficient,
            "result": result,
            "matched_columns": details,
            "columns": all_columns,
        }

        self.set_output("aggregate", aggregate)
        self.set_output("result", result)
        self.set_output("data", aggregate)

        if not details:
            self.set_output("summary", "No matching aggregate columns found")
            self.set_output("markdown", "No matching aggregate columns found")
            return

        summary = (
            f"{aggregate['result_name']} = {total:g} x {coefficient:g} = {result:g}; "
            f"matched {len(details)} column(s)."
        )
        detail_lines = [
            f"| File | Sheet | Column | Rows | Sum |",
            f"| --- | --- | --- | ---: | ---: |",
        ]
        for item in details:
            detail_lines.append(
                f"| {item['file']} | {item['sheet']} | {item['column']} | {item['rows']} | {item['sum']:g} |"
            )
        self.set_output("summary", summary)
        self.set_output("markdown", "\n".join([summary, "", *detail_lines]))

    def _calculate_number(self):
        if self.check_if_canceled("ExcelProcessor calculating"):
            return

        source_value = self._param.calculation_value
        if isinstance(source_value, str) and self._canvas.is_reff(source_value):
            self.set_input_value(source_value, self._canvas.get_variable_value(source_value))

        value = self._resolve_number(source_value, 0.0)
        coefficient = self._resolve_number(self._param.calculation_coefficient, 1.0)
        result = value * coefficient
        result_name = self._param.calculation_result_name or self._param.aggregate_result_name or "B"
        aggregate = {
            "result_name": result_name,
            "value": value,
            "coefficient": coefficient,
            "result": result,
            "operation": "multiply",
        }
        summary = f"{result_name} = {value:g} x {coefficient:g} = {result:g}"

        self.set_output("aggregate", aggregate)
        self.set_output("result", result)
        self.set_output("data", aggregate)
        self.set_output("summary", summary)
        self.set_output("markdown", summary)

    def _read_excels(self):
        """Read and parse Excel files into structured data."""
        all_data = {}
        summaries = []
        markdown_parts = []
        
        for file_ref in (self._param.input_files or []):
            if self.check_if_canceled("ExcelProcessor reading"):
                return
                
            # Get variable value
            value = self._canvas.get_variable_value(file_ref)
            self.set_input_value(file_ref, str(value)[:200] if value else "")
            
            if value is None:
                continue
            
            # Handle file content
            content, filename = self._get_file_content(file_ref)
            if content is None:
                continue
                
            # Parse Excel
            dfs = self._parse_excel_to_dataframes(content, filename)
            
            for sheet_name, df in dfs.items():
                key = f"{filename}_{sheet_name}" if len(dfs) > 1 else filename
                all_data[key] = df.to_dict(orient="records")
                
                # Build summary
                summaries.append(f"**{key}**: {len(df)} rows, {len(df.columns)} columns ({', '.join(df.columns.tolist()[:5])}{'...' if len(df.columns) > 5 else ''})")
                
                # Build markdown table
                markdown_parts.append(f"### {key}\n\n{df.head(10).to_markdown(index=False)}\n")
        
        # Set outputs
        self.set_output("data", all_data)
        self.set_output("summary", "\n".join(summaries) if summaries else "No Excel files found")
        self.set_output("markdown", "\n\n".join(markdown_parts) if markdown_parts else "No data")

    def _merge_excels(self):
        """Merge multiple Excel files/sheets into one."""
        all_dfs = []
        
        for file_ref in (self._param.input_files or []):
            if self.check_if_canceled("ExcelProcessor merging"):
                return
                
            value = self._canvas.get_variable_value(file_ref)
            self.set_input_value(file_ref, str(value)[:200] if value else "")
            
            if value is None:
                continue
                
            content, filename = self._get_file_content(file_ref)
            if content is None:
                continue
                
            dfs = self._parse_excel_to_dataframes(content, filename)
            all_dfs.extend(dfs.values())
        
        if not all_dfs:
            self.set_output("data", {})
            self.set_output("summary", "No data to merge")
            return
        
        # Merge strategy
        if self._param.merge_strategy == "concat":
            merged_df = pd.concat(all_dfs, ignore_index=True)
        elif self._param.merge_strategy == "join" and self._param.join_on:
            # Join on specified column
            merged_df = all_dfs[0]
            for df in all_dfs[1:]:
                merged_df = merged_df.merge(df, on=self._param.join_on, how="outer")
        else:
            merged_df = pd.concat(all_dfs, ignore_index=True)
        
        self.set_output("data", {"merged": merged_df.to_dict(orient="records")})
        self.set_output("summary", f"Merged {len(all_dfs)} sources into {len(merged_df)} rows, {len(merged_df.columns)} columns")
        self.set_output("markdown", merged_df.head(20).to_markdown(index=False))

    def _transform_data(self):
        """Apply transformations to data based on instructions or input data."""
        # Get the data to transform
        transform_ref = self._param.transform_data
        if not transform_ref:
            self.set_output("summary", "No transform data reference provided")
            return
            
        data = self._canvas.get_variable_value(transform_ref)
        self.set_input_value(transform_ref, str(data)[:300] if data else "")
        
        if data is None:
            self.set_output("summary", "Transform data is empty")
            return
        
        # Convert to DataFrame
        if isinstance(data, dict):
            # Could be {"sheet": [rows]} format
            if all(isinstance(v, list) for v in data.values()):
                # Multiple sheets
                all_markdown = []
                for sheet_name, rows in data.items():
                    df = pd.DataFrame(rows)
                    all_markdown.append(f"### {sheet_name}\n\n{df.to_markdown(index=False)}")
                self.set_output("data", data)
                self.set_output("markdown", "\n\n".join(all_markdown))
            else:
                df = pd.DataFrame([data])
                self.set_output("data", df.to_dict(orient="records"))
                self.set_output("markdown", df.to_markdown(index=False))
        elif isinstance(data, list):
            df = pd.DataFrame(data)
            self.set_output("data", df.to_dict(orient="records"))
            self.set_output("markdown", df.to_markdown(index=False))
        else:
            self.set_output("data", {"raw": str(data)})
            self.set_output("markdown", str(data))
        
        self.set_output("summary", "Transformed data ready for processing")

    def _output_excel(self):
        """Generate Excel file output from data."""
        # Get data from transform_data reference
        transform_ref = self._param.transform_data
        if not transform_ref:
            self.set_output("summary", "No data reference for output")
            return
            
        data = self._canvas.get_variable_value(transform_ref)
        self.set_input_value(transform_ref, str(data)[:300] if data else "")
        
        if data is None:
            self.set_output("summary", "No data to output")
            return
        
        try:
            # Prepare DataFrames
            if isinstance(data, dict):
                if all(isinstance(v, list) for v in data.values()):
                    # Multi-sheet format
                    dfs = {k: pd.DataFrame(v) for k, v in data.items()}
                else:
                    dfs = {"Sheet1": pd.DataFrame([data])}
            elif isinstance(data, list):
                dfs = {"Sheet1": pd.DataFrame(data)}
            else:
                self.set_output("summary", "Invalid data format for Excel output")
                return
            
            if self._param.output_format == "csv":
                # For CSV, only output first sheet
                first_df = list(dfs.values())[0]
                binary_content = first_df.to_csv(index=False).encode("utf-8")
                filename = f"{self._param.output_filename}.csv"
                mime_type = "text/csv"
            else:
                # Excel output
                excel_io = BytesIO()
                with pd.ExcelWriter(excel_io, engine='openpyxl') as writer:
                    for sheet_name, df in dfs.items():
                        # Sanitize sheet name (max 31 chars, no special chars)
                        safe_name = sheet_name[:31].replace("/", "_").replace("\\", "_")
                        df.to_excel(writer, sheet_name=safe_name, index=False)
                excel_io.seek(0)
                binary_content = excel_io.read()
                filename = f"{self._param.output_filename}.xlsx"
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            
            download_info = ArtifactService.create_download_info(
                self._canvas.get_tenant_id(),
                binary_content,
                filename,
                mime_type=mime_type,
                run_id=getattr(self._canvas, "_run_id", None),
                node_id=getattr(self, "_id", None),
            )
            self.set_output("downloads", [download_info])
            self.set_output("attachment", ArtifactService.attachment_from_download(download_info))
            
            total_rows = sum(len(df) for df in dfs.values())
            self.set_output("summary", f"Generated {filename} with {len(dfs)} sheet(s), {total_rows} total rows")
            self.set_output("data", {k: v.to_dict(orient="records") for k, v in dfs.items()})
            
            logging.info(f"ExcelProcessor: Generated {filename} as {download_info['doc_id']}")
            
        except Exception as e:
            logging.error(f"ExcelProcessor output error: {e}")
            self.set_output("summary", f"Error generating output: {str(e)}")

    def thoughts(self) -> str:
        """Return component thoughts for UI display."""
        op = self._param.operation
        if op == "read":
            return "Reading Excel files..."
        elif op == "merge":
            return "Merging Excel data..."
        elif op == "transform":
            return "Transforming data..."
        elif op in {"output", "export"}:
            return "Generating Excel output..."
        elif op == "aggregate":
            return "Aggregating Excel data..."
        elif op == "calculate":
            return "Calculating numeric result..."
        return "Processing Excel..."
