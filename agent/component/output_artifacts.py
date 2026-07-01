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

import html
import json
import math
import os
from abc import ABC
from copy import deepcopy
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from agent.artifact_service import ArtifactService
from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.file_service import FileService
from api.utils.api_utils import timeout


def _parse_json_like(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default
    return value if value is not None else default


def _as_list(value: Any) -> list[Any]:
    value = _parse_json_like(value, value)
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return deepcopy(value)
    return [deepcopy(value)]


def _as_dict(value: Any) -> dict[str, Any]:
    value = _parse_json_like(value, value)
    return deepcopy(value) if isinstance(value, dict) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def _safe_filename(name: str, fallback: str = "artifact") -> str:
    text = str(name or fallback).strip().replace("\\", " ").replace("/", " ")
    text = "".join(ch for ch in text if ch >= " " and ch not in '<>:"|?*#%')
    return text.strip(" .")[:160] or fallback


class ChartRendererParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.chart_spec = {}
        self.charts = []
        self.output_format = "svg"
        self.filename = "chart"
        self.outputs = {
            "chart_artifact": {"value": {}, "type": "Artifact"},
            "downloads": {"value": [], "type": "Array<Artifact>"},
            "markdown": {"value": "", "type": "string"},
            "html": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "chart_spec": {"type": "ChartSpec", "required": False},
            "charts": {"type": "Array<ChartSpec>", "required": False},
        }
        self.runtime_capabilities = {"produces_artifacts": True}

    def check(self):
        self.check_valid_value(self.output_format, "[ChartRenderer] Output format", ["svg", "html"])


class ChartRenderer(ComponentBase, ABC):
    component_name = "ChartRenderer"

    @staticmethod
    def _title(spec: dict[str, Any]) -> str:
        return str(spec.get("title") or spec.get("type") or "Chart")

    @staticmethod
    def _svg_frame(width: int, height: int, title: str, body: str) -> str:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">
<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>
<text x="24" y="34" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#1f2933">{html.escape(title)}</text>
{body}
</svg>"""

    @classmethod
    def _render_cartesian_svg(cls, spec: dict[str, Any], width: int = 720, height: int = 360) -> str:
        chart_type = spec.get("type") if spec.get("type") in {"line", "bar"} else "line"
        title = cls._title(spec)
        data = [item for item in (spec.get("data") or []) if isinstance(item, dict)]
        margin = {"left": 56, "right": 24, "top": 58, "bottom": 54}
        plot_w = width - margin["left"] - margin["right"]
        plot_h = height - margin["top"] - margin["bottom"]
        ys = [_number(item.get("y")) for item in data]
        y_min = min(0, min(ys) if ys else 0)
        y_max = max(100, max(ys) if ys else 100)
        if math.isclose(y_max, y_min):
            y_max = y_min + 1

        def x_pos(idx: int) -> float:
            if len(data) <= 1:
                return margin["left"] + plot_w / 2
            return margin["left"] + idx * plot_w / (len(data) - 1)

        def y_pos(value: float) -> float:
            return margin["top"] + (y_max - value) * plot_h / (y_max - y_min)

        grid = [
            f'<line x1="{margin["left"]}" y1="{margin["top"] + step * plot_h / 4:.1f}" x2="{width - margin["right"]}" y2="{margin["top"] + step * plot_h / 4:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
            for step in range(5)
        ]
        labels = []
        for idx, item in enumerate(data[:12]):
            labels.append(
                f'<text x="{x_pos(idx):.1f}" y="{height - 22}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#4b5563">{html.escape(str(item.get("x") or idx + 1))}</text>'
            )
        body = [
            *grid,
            f'<line x1="{margin["left"]}" y1="{margin["top"]}" x2="{margin["left"]}" y2="{height - margin["bottom"]}" stroke="#9aa4b2" stroke-width="1.2"/>',
            f'<line x1="{margin["left"]}" y1="{height - margin["bottom"]}" x2="{width - margin["right"]}" y2="{height - margin["bottom"]}" stroke="#9aa4b2" stroke-width="1.2"/>',
            *labels,
        ]
        if chart_type == "bar":
            bar_w = max(10, min(42, plot_w / max(1, len(data)) * 0.58))
            for idx, item in enumerate(data):
                value = _number(item.get("y"))
                x = x_pos(idx) - bar_w / 2
                y = y_pos(value)
                body.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{height - margin["bottom"] - y:.1f}" rx="3" fill="#3976d3"/>'
                )
        else:
            points = " ".join(f"{x_pos(idx):.1f},{y_pos(_number(item.get('y'))):.1f}" for idx, item in enumerate(data))
            if points:
                body.append(f'<polyline points="{points}" fill="none" stroke="#3976d3" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
            for idx, item in enumerate(data):
                body.append(f'<circle cx="{x_pos(idx):.1f}" cy="{y_pos(_number(item.get("y"))):.1f}" r="4" fill="#ffb020" stroke="#1f2933" stroke-width="1"/>')
        return cls._svg_frame(width, height, title, "\n".join(body))

    @classmethod
    def _render_radar_svg(cls, spec: dict[str, Any], width: int = 560, height: int = 420) -> str:
        title = cls._title(spec)
        dimensions = [str(item) for item in (spec.get("dimensions") or []) if str(item).strip()]
        series = [item for item in (spec.get("series") or []) if isinstance(item, dict)]
        cx, cy, radius = width / 2, height / 2 + 18, min(width, height) * 0.32
        axes = []
        for idx, dim in enumerate(dimensions):
            angle = -math.pi / 2 + idx * 2 * math.pi / max(1, len(dimensions))
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            label_x = cx + (radius + 30) * math.cos(angle)
            label_y = cy + (radius + 30) * math.sin(angle)
            axes.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#d1d5db" stroke-width="1"/>')
            axes.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#4b5563">{html.escape(dim)}</text>')
        rings = []
        for level in range(1, 5):
            r = radius * level / 4
            rings.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="#edf0f3" stroke-width="1"/>')
        polygons = []
        colors = ["#3976d3", "#ffb020", "#3cb179", "#c85560"]
        for idx, item in enumerate(series[:4]):
            values = item.get("values") or []
            by_axis = {str(v.get("axis")): _number(v.get("value")) for v in values if isinstance(v, dict)}
            points = []
            for dim_idx, dim in enumerate(dimensions):
                angle = -math.pi / 2 + dim_idx * 2 * math.pi / max(1, len(dimensions))
                value_radius = radius * max(0, min(100, by_axis.get(dim, 0))) / 100
                points.append(f"{cx + value_radius * math.cos(angle):.1f},{cy + value_radius * math.sin(angle):.1f}")
            color = colors[idx % len(colors)]
            polygons.append(f'<polygon points="{" ".join(points)}" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="2"/>')
        return cls._svg_frame(width, height, title, "\n".join([*rings, *axes, *polygons]))

    @classmethod
    def render_svg(cls, spec: dict[str, Any]) -> str:
        if not isinstance(spec, dict):
            raise ValueError("ChartRenderer requires a ChartSpec object")
        if spec.get("type") == "radar":
            return cls._render_radar_svg(spec)
        return cls._render_cartesian_svg(spec)

    @classmethod
    def render_html(cls, charts: list[dict[str, Any]]) -> str:
        svgs = [cls.render_svg(spec) for spec in charts if isinstance(spec, dict)]
        return "<!doctype html><html><head><meta charset=\"utf-8\"><title>Charts</title></head><body>" + "\n".join(svgs) + "</body></html>"

    @staticmethod
    def build_markdown(download: dict[str, Any], title: str) -> str:
        url = download.get("download_url") or ""
        filename = download.get("filename") or "chart.svg"
        if str(filename).endswith(".svg"):
            return f"![{title}]({url})"
        return f"[{title}]({url})"

    @classmethod
    def create_chart_download(
        cls,
        *,
        tenant_id: str,
        chart_spec: dict[str, Any] | None = None,
        charts: list[dict[str, Any]] | None = None,
        output_format: str = "svg",
        filename: str = "chart",
        run_id: str | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        chart_list = charts or ([chart_spec] if chart_spec else [])
        if not chart_list:
            raise ValueError("ChartRenderer requires chart_spec or charts")
        safe_name = _safe_filename(filename or cls._title(chart_list[0]), "chart")
        if output_format == "html":
            content = cls.render_html(chart_list).encode("utf-8")
            filename = f"{safe_name}.html"
            mime_type = "text/html"
        else:
            content = cls.render_svg(chart_list[0]).encode("utf-8")
            filename = f"{safe_name}.svg"
            mime_type = "image/svg+xml"
        return ArtifactService.create_download_info(
            tenant_id,
            content,
            filename,
            mime_type=mime_type,
            run_id=run_id,
            node_id=node_id,
            include_base64=False,
            metadata={"kind": "chart", "chart_count": len(chart_list)},
        )

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        chart_spec = _as_dict(self._resolve(self._param.chart_spec))
        charts = _as_list(self._resolve(self._param.charts))
        download = self.create_chart_download(
            tenant_id=self._canvas.get_tenant_id(),
            chart_spec=chart_spec,
            charts=[item for item in charts if isinstance(item, dict)],
            output_format=self._param.output_format,
            filename=self._param.filename,
            run_id=getattr(self._canvas, "_run_id", None),
            node_id=getattr(self, "_id", None),
        )
        attachment = ArtifactService.attachment_from_download(download)
        markdown = self.build_markdown(download, chart_spec.get("title") or self._param.filename or "Chart")
        self.set_output("chart_artifact", attachment)
        self.set_output("downloads", [download])
        self.set_output("markdown", markdown)
        self.set_output("html", self.render_html([chart_spec] if chart_spec else charts))


class ArtifactPackagerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.artifacts = []
        self.manifest = {}
        self.filename = "agent_outputs"
        self.outputs = {
            "package": {"value": {}, "type": "Artifact"},
            "downloads": {"value": [], "type": "Array<Artifact>"},
            "manifest": {"value": {}, "type": "JSON"},
            "markdown": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "artifacts": {"type": "Array<Artifact>", "required": True},
            "manifest": {"type": "JSON", "required": False},
        }
        self.runtime_capabilities = {"produces_artifacts": True}

    def check(self):
        return True


class ArtifactPackager(ComponentBase, ABC):
    component_name = "ArtifactPackager"

    @staticmethod
    def normalize_artifact(value: Any) -> dict[str, Any] | None:
        if isinstance(value, str):
            value = _parse_json_like(value, None)
        if not isinstance(value, dict):
            return None
        doc_id = value.get("doc_id") or value.get("artifact_id")
        filename = value.get("filename") or value.get("file_name") or value.get("name") or f"{doc_id or 'artifact'}.bin"
        if not doc_id:
            return None
        return {
            "artifact_id": value.get("artifact_id") or doc_id,
            "doc_id": doc_id,
            "filename": _safe_filename(filename, "artifact.bin"),
            "mime_type": value.get("mime_type") or ArtifactService.guess_mime_type(filename),
            "size": value.get("size"),
            "download_url": value.get("download_url") or f"/v1/agents/download?id={doc_id}",
        }

    @classmethod
    def normalize_artifacts(cls, artifacts: Any) -> list[dict[str, Any]]:
        result = []
        seen = set()
        for item in _as_list(artifacts):
            artifact = cls.normalize_artifact(item)
            if not artifact:
                continue
            key = artifact["doc_id"]
            if key in seen:
                continue
            seen.add(key)
            result.append(artifact)
        return result

    @classmethod
    def build_manifest(cls, artifacts: list[dict[str, Any]], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "schema_version": 1,
            **_as_dict(manifest),
            "artifacts": deepcopy(artifacts),
            "artifact_count": len(artifacts),
        }

    @classmethod
    def build_zip_bytes(cls, tenant_id: str, artifacts: list[dict[str, Any]], manifest: dict[str, Any], fetcher=FileService.get_blob) -> bytes:
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
            used_names = {"manifest.json"}
            for item in artifacts:
                filename = _safe_filename(item.get("filename"), item.get("doc_id") or "artifact.bin")
                base, ext = os.path.splitext(filename)
                candidate = filename
                idx = 2
                while candidate in used_names:
                    candidate = f"{base}_{idx}{ext}"
                    idx += 1
                used_names.add(candidate)
                try:
                    content = fetcher(tenant_id, item["doc_id"])
                except Exception as exc:
                    zf.writestr(f"{candidate}.error.txt", f"Unable to fetch artifact {item['doc_id']}: {exc}")
                    continue
                zf.writestr(candidate, content)
        return buffer.getvalue()

    @classmethod
    def create_package_download(
        cls,
        *,
        tenant_id: str,
        artifacts: list[dict[str, Any]],
        manifest: dict[str, Any] | None = None,
        filename: str = "agent_outputs",
        run_id: str | None = None,
        node_id: str | None = None,
        fetcher=FileService.get_blob,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        normalized = cls.normalize_artifacts(artifacts)
        package_manifest = cls.build_manifest(normalized, manifest)
        content = cls.build_zip_bytes(tenant_id, normalized, package_manifest, fetcher=fetcher)
        safe_name = _safe_filename(filename, "agent_outputs")
        download = ArtifactService.create_download_info(
            tenant_id,
            content,
            f"{safe_name}.zip",
            mime_type="application/zip",
            run_id=run_id,
            node_id=node_id,
            include_base64=False,
            metadata={"kind": "artifact_package", "artifact_count": len(normalized)},
        )
        return download, package_manifest

    @staticmethod
    def build_markdown(download: dict[str, Any]) -> str:
        return f"[{download.get('filename') or 'agent_outputs.zip'}]({download.get('download_url') or ''})"

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        artifacts = self.normalize_artifacts(self._resolve(self._param.artifacts))
        manifest = _as_dict(self._resolve(self._param.manifest))
        download, package_manifest = self.create_package_download(
            tenant_id=self._canvas.get_tenant_id(),
            artifacts=artifacts,
            manifest=manifest,
            filename=self._param.filename,
            run_id=getattr(self._canvas, "_run_id", None),
            node_id=getattr(self, "_id", None),
        )
        self.set_output("package", ArtifactService.attachment_from_download(download))
        self.set_output("downloads", [download])
        self.set_output("manifest", package_manifest)
        self.set_output("markdown", self.build_markdown(download))
