#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskModelService


class TaskTaxonomyError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": str(self), "details": self.details}


DEFAULT_TAXONOMIES = {
    "task_type": {
        "categories": {
            "find_file": ["find", "search", "找到", "查找", "最近"],
            "read_document": ["read", "open", "读取", "打开"],
            "edit_document": ["edit", "modify", "修改", "新增", "补充"],
            "compare_documents": ["compare", "diff", "比对", "比较", "冲突"],
            "generate_report": ["report", "报告", "输出报告"],
            "run_workflow": ["run", "execute", "运行", "执行", "测试"],
            "needs_clarification": ["不清楚", "clarify"],
        }
    },
    "failure_type": {
        "categories": {
            "incomplete_output": ["missing output", "缺输出", "completion"],
            "missing_evidence": ["evidence", "证据", "source_ref"],
            "unresolved_dependency": ["dependency", "依赖", "blocked"],
            "policy_violation": ["policy", "违规", "安全"],
            "ambiguous_progress": ["ambiguous", "模糊", "未推进"],
        }
    },
}


class TaskTaxonomyService:
    _taxonomies: dict[str, dict[str, dict[str, Any]]] = {}

    @classmethod
    def reset(cls) -> None:
        cls._taxonomies = {}

    @classmethod
    def ensure_defaults(cls) -> None:
        for name, payload in DEFAULT_TAXONOMIES.items():
            if name not in cls._taxonomies:
                cls.create_taxonomy(name=name, version="v1", categories=payload["categories"], metadata={"default": True})
                cls.freeze_version(name=name, version="v1")

    @classmethod
    def create_taxonomy(
        cls,
        *,
        name: str,
        version: str = "v1",
        categories: dict[str, list[str]] | list[str] | None = None,
        examples: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = cls.normalize_name(name)
        version = cls.normalize_version(version)
        cls._taxonomies.setdefault(name, {})
        if version in cls._taxonomies[name]:
            raise TaskTaxonomyError("TAXONOMY_VERSION_EXISTS", "Taxonomy version already exists.", {"name": name, "version": version})
        item = {
            "schema_version": 1,
            "name": name,
            "version": version,
            "status": "draft",
            "categories": cls.normalize_categories(categories),
            "examples": cls.normalize_examples(examples),
            "metadata": deepcopy(metadata or {}),
            "created_at": cls.now(),
            "updated_at": cls.now(),
        }
        cls._taxonomies[name][version] = item
        return deepcopy(item)

    @classmethod
    def get_taxonomy(cls, *, name: str, version: str = "") -> dict[str, Any]:
        cls.ensure_defaults()
        name = cls.normalize_name(name)
        if name not in cls._taxonomies:
            raise TaskTaxonomyError("TAXONOMY_NOT_FOUND", "Taxonomy not found.", {"name": name})
        version = cls.normalize_version(version) if version else cls.latest_version(name)
        if version not in cls._taxonomies[name]:
            raise TaskTaxonomyError("TAXONOMY_VERSION_NOT_FOUND", "Taxonomy version not found.", {"name": name, "version": version})
        return deepcopy(cls._taxonomies[name][version])

    @classmethod
    def update_taxonomy(
        cls,
        *,
        name: str,
        version: str,
        categories: dict[str, list[str]] | list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = cls._mutable(name, version)
        if categories is not None:
            item["categories"] = cls.normalize_categories(categories)
        if metadata:
            item["metadata"].update(deepcopy(metadata))
        item["updated_at"] = cls.now()
        return deepcopy(item)

    @classmethod
    def freeze_version(cls, *, name: str, version: str) -> dict[str, Any]:
        item = cls._mutable(name, version)
        item["status"] = "frozen"
        item["updated_at"] = cls.now()
        return deepcopy(item)

    @classmethod
    def fork_version(cls, *, name: str, from_version: str, new_version: str) -> dict[str, Any]:
        source = cls.get_taxonomy(name=name, version=from_version)
        name = source["name"]
        new_version = cls.normalize_version(new_version)
        if new_version in cls._taxonomies.get(name, {}):
            raise TaskTaxonomyError("TAXONOMY_VERSION_EXISTS", "Taxonomy version already exists.", {"name": name, "version": new_version})
        forked = deepcopy(source)
        forked["version"] = new_version
        forked["status"] = "draft"
        forked["created_at"] = cls.now()
        forked["updated_at"] = cls.now()
        forked["metadata"] = {**forked.get("metadata", {}), "forked_from": source["version"]}
        cls._taxonomies[name][new_version] = forked
        return deepcopy(forked)

    @classmethod
    def add_example(
        cls,
        *,
        name: str,
        version: str,
        category: str,
        text: str,
        example_type: str = "positive",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = cls._mutable(name, version)
        category = str(category or "").strip()
        if category not in item["categories"]:
            raise TaskTaxonomyError("CATEGORY_NOT_FOUND", "Category not found.", {"category": category})
        example_type = example_type if example_type in {"positive", "negative", "edge"} else "positive"
        example = {
            "example_id": AgentTaskModelService.new_id("example"),
            "category": category,
            "text": str(text or ""),
            "example_type": example_type,
            "metadata": deepcopy(metadata or {}),
            "created_at": cls.now(),
        }
        item["examples"].setdefault(example_type, []).append(example)
        item["updated_at"] = cls.now()
        return deepcopy(example)

    @classmethod
    def classify(cls, *, name: str, text: str, version: str = "") -> dict[str, Any]:
        taxonomy = cls.get_taxonomy(name=name, version=version)
        lowered = str(text or "").lower()
        scores: dict[str, float] = {category: 0.0 for category in taxonomy["categories"]}
        matched_terms: dict[str, list[str]] = {category: [] for category in taxonomy["categories"]}
        for category, terms in taxonomy["categories"].items():
            for term in terms:
                if str(term).lower() in lowered:
                    scores[category] += 1.0
                    matched_terms[category].append(term)
        for example in taxonomy["examples"].get("positive", []):
            if example["text"].lower() and example["text"].lower() in lowered:
                scores[example["category"]] += 2.0
                matched_terms[example["category"]].append(f"example:{example['example_id']}")
        for example in taxonomy["examples"].get("negative", []):
            if example["text"].lower() and example["text"].lower() in lowered:
                scores[example["category"]] -= 2.0
        best_category, best_score = max(scores.items(), key=lambda item: item[1]) if scores else ("unsupported", 0.0)
        if best_score <= 0:
            best_category = "needs_clarification" if "needs_clarification" in taxonomy["categories"] else "unsupported"
        confidence = 0.25 if best_score <= 0 else min(0.95, 0.45 + best_score * 0.15)
        return {
            "schema_version": 1,
            "taxonomy_name": taxonomy["name"],
            "taxonomy_version": taxonomy["version"],
            "category": best_category,
            "confidence": round(confidence, 2),
            "matched_terms": matched_terms.get(best_category, []),
            "needs_clarification": best_category in {"needs_clarification", "unsupported"},
        }

    @classmethod
    def evaluate(cls, *, name: str, examples: list[dict[str, Any]], version: str = "") -> dict[str, Any]:
        results = []
        correct = 0
        unsupported = 0
        needs_clarification = 0
        for item in examples:
            expected = str(item.get("expected_category") or item.get("category") or "")
            predicted = cls.classify(name=name, version=version, text=str(item.get("text") or ""))
            ok = predicted["category"] == expected
            correct += 1 if ok else 0
            unsupported += 1 if predicted["category"] == "unsupported" else 0
            needs_clarification += 1 if predicted["needs_clarification"] else 0
            results.append({"text": item.get("text", ""), "expected_category": expected, "predicted": predicted, "ok": ok})
        total = len(examples)
        return {
            "schema_version": 1,
            "taxonomy_name": cls.normalize_name(name),
            "taxonomy_version": cls.get_taxonomy(name=name, version=version)["version"],
            "total": total,
            "accuracy": round(correct / total, 4) if total else 0.0,
            "unsupported_case_rate": round(unsupported / total, 4) if total else 0.0,
            "needs_clarification_rate": round(needs_clarification / total, 4) if total else 0.0,
            "results": results,
        }

    @classmethod
    def _mutable(cls, name: str, version: str) -> dict[str, Any]:
        taxonomy = cls.get_taxonomy(name=name, version=version)
        item = cls._taxonomies[taxonomy["name"]][taxonomy["version"]]
        if item["status"] == "frozen":
            raise TaskTaxonomyError("TAXONOMY_VERSION_FROZEN", "Frozen taxonomy version cannot be modified.", {"name": name, "version": version})
        return item

    @classmethod
    def latest_version(cls, name: str) -> str:
        versions = sorted(cls._taxonomies.get(name, {}).keys())
        if not versions:
            raise TaskTaxonomyError("TAXONOMY_NOT_FOUND", "Taxonomy not found.", {"name": name})
        return versions[-1]

    @staticmethod
    def normalize_categories(categories: dict[str, list[str]] | list[str] | None) -> dict[str, list[str]]:
        if isinstance(categories, dict):
            return {str(key): [str(term) for term in (value or [])] for key, value in categories.items()}
        if isinstance(categories, list):
            return {str(item): [] for item in categories}
        return {}

    @staticmethod
    def normalize_examples(examples: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
        result = {"positive": [], "negative": [], "edge": []}
        if not isinstance(examples, dict):
            return result
        for key in result:
            result[key] = [deepcopy(item) for item in examples.get(key, []) if isinstance(item, dict)]
        return result

    @staticmethod
    def normalize_name(name: str) -> str:
        value = str(name or "").strip()
        if not value:
            raise TaskTaxonomyError("INVALID_TAXONOMY_NAME", "Taxonomy name is required.")
        return value

    @staticmethod
    def normalize_version(version: str) -> str:
        value = str(version or "").strip()
        if not value:
            raise TaskTaxonomyError("INVALID_TAXONOMY_VERSION", "Taxonomy version is required.")
        return value

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()


class TaskFeedbackService:
    _feedback: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        cls._feedback = []

    @classmethod
    def record(
        cls,
        *,
        run_id: str = "",
        task_id: str = "",
        taxonomy_name: str,
        taxonomy_version: str,
        input_text: str = "",
        predicted_category: str = "",
        correct: bool = False,
        suggested_category: str = "",
        reason: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = {
            "feedback_id": AgentTaskModelService.new_id("feedback"),
            "run_id": str(run_id or ""),
            "task_id": str(task_id or ""),
            "taxonomy_name": str(taxonomy_name or ""),
            "taxonomy_version": str(taxonomy_version or ""),
            "input_text": str(input_text or ""),
            "predicted_category": str(predicted_category or ""),
            "correct": bool(correct),
            "suggested_category": str(suggested_category or ""),
            "reason": str(reason or ""),
            "user_id": str(user_id or ""),
            "metadata": deepcopy(metadata or {}),
            "created_at": TaskTaxonomyService.now(),
        }
        cls._feedback.append(item)
        return deepcopy(item)

    @classmethod
    def list(
        cls,
        *,
        run_id: str = "",
        task_id: str = "",
        taxonomy_name: str = "",
        taxonomy_version: str = "",
    ) -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in cls._feedback
            if (not run_id or item["run_id"] == run_id)
            and (not task_id or item["task_id"] == task_id)
            and (not taxonomy_name or item["taxonomy_name"] == taxonomy_name)
            and (not taxonomy_version or item["taxonomy_version"] == taxonomy_version)
        ]

    @classmethod
    def summarize(cls, *, taxonomy_name: str = "", taxonomy_version: str = "") -> dict[str, Any]:
        items = cls.list(taxonomy_name=taxonomy_name, taxonomy_version=taxonomy_version)
        total = len(items)
        correct = len([item for item in items if item["correct"]])
        suggestions: dict[str, int] = {}
        for item in items:
            if item["suggested_category"]:
                suggestions[item["suggested_category"]] = suggestions.get(item["suggested_category"], 0) + 1
        return {
            "schema_version": 1,
            "total": total,
            "correct": correct,
            "incorrect": total - correct,
            "accuracy_from_feedback": round(correct / total, 4) if total else 0.0,
            "suggested_categories": suggestions,
        }
