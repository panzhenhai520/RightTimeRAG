#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from api.db.services.document_normalize_service import DocumentNormalizeService
from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService


FILE_GOAL_TYPES = {"find_file", "read_document", "edit_document", "compare_documents", "extract_information", "generate_report"}


class RelevantFileResolver:
    @classmethod
    def resolve(
        cls,
        *,
        goal_intent: dict[str, Any],
        root: str = "",
        path: str = ".",
        roots: list[str | Path] | None = None,
        query: str = "",
        extensions: list[str] | str | None = None,
        max_candidates: int = 8,
    ) -> dict[str, Any]:
        terms = cls.query_terms(goal_intent, query=query)
        search_query = " ".join(terms[:3])
        files = []
        if search_query:
            files = WorkspaceFileService.search_files(
                query=search_query,
                root=root,
                path=path,
                roots=roots,
                extensions=extensions,
                max_results=max(20, max_candidates * 4),
            )["files"]
        if not files:
            files = WorkspaceFileService.list_files(
                root=root,
                path=path,
                roots=roots,
                recursive=True,
                include_dirs=False,
                extensions=extensions,
                max_results=max(50, max_candidates * 6),
            )["files"]
        scored = [cls.score_file(item, goal_intent=goal_intent, terms=terms) for item in files]
        scored.sort(key=lambda item: (item["score"], item["file"].get("modified_at", 0)), reverse=True)
        return {
            "candidate_files": scored[: max(1, int(max_candidates or 8))],
            "query_terms": terms,
            "unresolved_context": [] if scored else [{"kind": "no_candidate_files", "message": "No relevant file candidates found."}],
        }

    @staticmethod
    def query_terms(goal_intent: dict[str, Any], *, query: str = "") -> list[str]:
        raw = " ".join(
            str(item or "")
            for item in [
                query,
                goal_intent.get("primary_object"),
                goal_intent.get("raw_request"),
                goal_intent.get("expected_outcome"),
            ]
        )
        terms = []
        for token in re.findall(r"[\w\u4e00-\u9fff.-]{2,}", raw.lower()):
            if token in {"target_document", "document_pair", "revision_plan", "comparison_report"}:
                continue
            if token not in terms:
                terms.append(token)
        for term in ("任务分解", "执行闭环", "计划", "文档", "合同", "法律", "报告", "条款", "测试", "接口", "安全"):
            if term in raw and term not in terms:
                terms.append(term)
        return terms[:20]

    @staticmethod
    def score_file(file_info: dict[str, Any], *, goal_intent: dict[str, Any], terms: list[str]) -> dict[str, Any]:
        name = str(file_info.get("name") or "").lower()
        rel = str(file_info.get("relative_path") or "").lower()
        score = 0.0
        reasons = []
        for term in terms:
            if term and term in name:
                score += 3.0
                reasons.append(f"name_match:{term}")
            elif term and term in rel:
                score += 1.5
                reasons.append(f"path_match:{term}")
        content = ""
        path = file_info.get("path")
        try:
            if path and file_info.get("size", 0) <= 256 * 1024 and file_info.get("extension") in {".md", ".txt", ".json", ".py", ".ts", ".tsx"}:
                content = Path(str(path)).read_text(encoding="utf-8", errors="ignore").lower()[:65536]
        except Exception:
            content = ""
        for term in terms:
            if term and term in content:
                score += 1.0
                reasons.append(f"content_match:{term}")
        if any(term in str(goal_intent.get("raw_request") or "") for term in ("最近", "上次", "最新")):
            score += min(float(file_info.get("modified_at") or 0) / 10000000000, 1.0)
            reasons.append("recent_hint")
        if file_info.get("extension") in {".md", ".txt", ".docx", ".pdf", ".xlsx", ".csv", ".json"}:
            score += 0.5
            reasons.append("supported_extension")
        return {"file": file_info, "score": round(score, 4), "reasons": reasons}


class RecentArtifactFinder:
    @staticmethod
    def find(artifacts: list[dict[str, Any]] | None = None, *, query: str = "", max_results: int = 5) -> list[dict[str, Any]]:
        items = [item for item in (artifacts or []) if isinstance(item, dict)]
        lowered = str(query or "").lower()
        if lowered:
            items = [
                item
                for item in items
                if lowered in str(item.get("filename") or item.get("file_name") or item.get("name") or "").lower()
            ]
        items.sort(key=lambda item: item.get("created_at") or item.get("modified_at") or 0, reverse=True)
        return items[: max(1, int(max_results or 5))]


class TaskContextCollector:
    @classmethod
    def collect(
        cls,
        *,
        goal_intent: dict[str, Any],
        root: str = "",
        path: str = ".",
        roots: list[str | Path] | None = None,
        query: str = "",
        extensions: list[str] | str | None = None,
        max_candidates: int = 8,
        normalize_top: int = 0,
        recent_runs: list[dict[str, Any]] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        candidate_files = []
        unresolved = []
        evidence = []
        document_outlines = []
        if goal_intent.get("goal_type") in FILE_GOAL_TYPES:
            try:
                resolved = RelevantFileResolver.resolve(
                    goal_intent=goal_intent,
                    root=root,
                    path=path,
                    roots=roots,
                    query=query,
                    extensions=extensions,
                    max_candidates=max_candidates,
                )
                candidate_files = resolved["candidate_files"]
                unresolved.extend(resolved["unresolved_context"])
                evidence.extend(
                    {
                        "source_ref": item["file"].get("relative_path") or item["file"].get("path"),
                        "score": item["score"],
                        "reasons": item["reasons"],
                    }
                    for item in candidate_files
                )
            except WorkspaceFileError as exc:
                unresolved.append(exc.to_dict())
        for item in candidate_files[: max(0, int(normalize_top or 0))]:
            file_info = item["file"]
            try:
                normalize_roots = roots
                if normalize_roots is None:
                    root_path = Path(str(root)).expanduser() if root else None
                    normalize_roots = [root_path] if root_path and root_path.exists() else [Path(file_info["path"]).parent]
                document = DocumentNormalizeService.normalize(
                    path=file_info["path"],
                    roots=normalize_roots,
                    max_bytes=256 * 1024,
                    chunk_chars=1600,
                )
                document_outlines.append(cls.outline_from_document(document))
            except Exception as exc:
                unresolved.append({"kind": "normalize_failed", "path": file_info.get("path"), "message": str(exc)})
        artifact_matches = RecentArtifactFinder.find(artifacts, query=query or goal_intent.get("primary_object", ""), max_results=5)
        return {
            "schema_version": 1,
            "goal_id": goal_intent.get("goal_id", ""),
            "goal_type": goal_intent.get("goal_type", ""),
            "candidate_files": candidate_files,
            "candidate_artifacts": artifact_matches,
            "recent_runs": list(recent_runs or [])[:5],
            "document_outlines": document_outlines,
            "evidence": evidence,
            "unresolved_context": unresolved,
            "summary": {
                "candidate_file_count": len(candidate_files),
                "candidate_artifact_count": len(artifact_matches),
                "recent_run_count": len(list(recent_runs or [])[:5]),
                "document_outline_count": len(document_outlines),
                "unresolved_count": len(unresolved),
            },
        }

    @staticmethod
    def outline_from_document(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "document_id": document.get("document_id", ""),
            "filename": document.get("filename", ""),
            "source_path": document.get("source_path", ""),
            "sections": [
                {
                    "title": item.get("title"),
                    "level": item.get("level"),
                    "section_path": item.get("section_path", []),
                    "source_ref": item.get("source_ref", ""),
                }
                for item in document.get("sections", [])
            ],
            "metadata": document.get("metadata", {}),
            "audit": document.get("audit", {}),
        }
