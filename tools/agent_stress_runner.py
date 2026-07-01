#!/usr/bin/env python
#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

import argparse
import json
import os
import sys
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from agent.artifact_service import ArtifactService
from agent.component.chart_spec_builder import ChartSpecBuilder
from agent.component.number_calculate import NumberCalculate
from agent.component.output_artifacts import ArtifactPackager, ChartRenderer
from agent.component.scoped_db import ScopedDB
from agent.component import scoped_db as scoped_db_module
from agent.sql_guard import prepare_readonly_sqls
from api.db.services import agent_document_write_coordinator_service as doc_write_module
from api.db.services.agent_document_write_coordinator_service import AgentDocumentWriteCoordinatorService
from common import settings


class FakeStorage:
    def __init__(self):
        self.saved: dict[tuple[str, str], bytes] = {}

    def put(self, tenant_id: str, doc_id: str, content: bytes):
        self.saved[(tenant_id, doc_id)] = content


class FakeRedisKV:
    def __init__(self):
        self.saved: dict[str, str] = {}

    def get(self, key: str):
        return self.saved.get(key)

    def set_obj(self, key: str, value: Any, ttl: int | None = None):
        self.saved[key] = json.dumps(value, ensure_ascii=False)
        return True


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 6)


def assert_blocked(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


def run_iteration(index: int, storage: FakeStorage) -> dict[str, Any]:
    started = time.perf_counter()
    tenant_id = f"stress-tenant-{index % 3}"
    run_id = f"stress-run-{index}"
    agent_id = "stress_teacher_agent"
    queue_wait_s = 0.001 * (index % 5)

    db_ref = ScopedDB.connector_ref(tenant_id, agent_id)
    table_ref = ScopedDB.ensure_table(db_ref, "student_score")
    self_score = 80 + (index % 11)
    external_score = 84 + (index % 9)
    final_score = NumberCalculate.weighted_score(self_score, 0.6, external_score, 0.4)
    row = ScopedDB.insert_record(
        table_ref,
        {
            "id": f"score-{index}",
            "student_id": f"student-{index % 7}",
            "activity_id": f"lesson-{index}",
            "score": final_score,
            "self_score": self_score,
            "external_score": external_score,
            "rubric_json": {"pronunciation": self_score, "fluency": external_score},
        },
    )
    query = ScopedDB.query_records(table_ref, {"student_id": row["student_id"]}, limit=20)
    chart = ChartSpecBuilder.build_spec(
        "line",
        [
            {"activity": "baseline", "score": 78},
            {"activity": row["activity_id"], "score": final_score},
        ],
        title=f"stress chart {index}",
        x_field="activity",
        y_field="score",
    )
    chart_download = ChartRenderer.create_chart_download(
        tenant_id=tenant_id,
        chart_spec=chart,
        filename=f"stress_chart_{index}",
        run_id=run_id,
        node_id="ChartRenderer:Stress",
    )
    note_download = ArtifactService.create_download_info(
        tenant_id,
        json.dumps({"run_id": run_id, "score": final_score}, ensure_ascii=False).encode("utf-8"),
        f"stress_note_{index}.json",
        mime_type="application/json",
        run_id=run_id,
        node_id="Artifact:StressNote",
        include_base64=False,
    )
    package_download, package_manifest = ArtifactPackager.create_package_download(
        tenant_id=tenant_id,
        artifacts=[chart_download, note_download],
        manifest={"run_id": run_id, "mode": "stress"},
        filename=f"stress_outputs_{index}",
        run_id=run_id,
        node_id="ArtifactPackager:Stress",
        fetcher=lambda t, d: storage.saved[(t, d)],
    )
    document_id = f"shared-doc-{index}"
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id=tenant_id,
        document_id=document_id,
        version=1,
        content="课堂记录：\n",
        audit={"meeting_id": f"meeting-{index}", "turn_id": f"turn-{index}", "operator": "stress_import"},
    )
    patch_proposal = AgentDocumentWriteCoordinatorService.build_patch_proposal(
        proposal_id=f"proposal-{index}",
        base_document_id=document_id,
        base_version=1,
        agent_id=agent_id,
        run_id=run_id,
        summary="追加课堂成绩摘要",
        patches=[{"operation": "append", "text": f"lesson-{index}: final_score={final_score}\n"}],
        confidence=0.9,
    )
    AgentDocumentWriteCoordinatorService.submit_patch_proposal(tenant_id=tenant_id, proposal=patch_proposal)
    write_result = AgentDocumentWriteCoordinatorService.apply_write_request(
        tenant_id=tenant_id,
        document_id=document_id,
        expected_version=1,
        selected_proposals=[patch_proposal["proposal_id"]],
        audit={"meeting_id": f"meeting-{index}", "turn_id": f"turn-{index}", "operator": "stress_god"},
    )
    version_conflict_blocked = assert_blocked(
        lambda: AgentDocumentWriteCoordinatorService.apply_write_request(
            tenant_id=tenant_id,
            document_id=document_id,
            expected_version=1,
            selected_proposals=[patch_proposal["proposal_id"]],
        )
    )
    elapsed = time.perf_counter() - started
    return {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "status": "completed",
        "queue_wait_s": queue_wait_s,
        "worker_duration_s": round(elapsed, 6),
        "artifact_count": package_manifest["artifact_count"] + 1,
        "artifact_docs": [chart_download["doc_id"], note_download["doc_id"], package_download["doc_id"]],
        "row_count": query["row_count"],
        "final_score": final_score,
        "document_write_version": write_result["new_version"],
        "version_conflict_blocked": version_conflict_blocked,
    }


def build_report(mode: str, iterations: int, results: list[dict[str, Any]], elapsed_s: float, report_dir: str) -> dict[str, Any]:
    completed = [item for item in results if item.get("status") == "completed"]
    worker_durations = [float(item.get("worker_duration_s") or 0) for item in results]
    queue_waits = [float(item.get("queue_wait_s") or 0) for item in results]
    artifact_total = sum(int(item.get("artifact_count") or 0) for item in results)
    artifact_success = sum(1 for item in results for doc_id in item.get("artifact_docs", []) if doc_id)
    final_status_consistent = len(completed) == iterations and len({item["run_id"] for item in completed}) == iterations
    blocked_checks = {
        "dangerous_sql": assert_blocked(lambda: prepare_readonly_sqls("DELETE FROM users")),
        "unsafe_table_template": assert_blocked(lambda: ScopedDB.safe_table_name("agent", "drop table users")),
        "cross_tenant_db": assert_blocked(lambda: ScopedDB.assert_tenant(ScopedDB.connector_ref("tenant-a", "agent-a"), "tenant-b")),
        "document_version_conflict": all(item.get("version_conflict_blocked") for item in completed),
    }
    success_rate = len(completed) / max(iterations, 1)
    artifact_success_rate = artifact_success / max(artifact_total, 1)
    report = {
        "schema_version": 1,
        "mode": mode,
        "iterations": iterations,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed_s, 6),
        "success_rate": round(success_rate, 6),
        "artifact_success_rate": round(artifact_success_rate, 6),
        "task_final_status_consistency": final_status_consistent,
        "unsafe_operation_blocked": all(blocked_checks.values()),
        "blocked_checks": blocked_checks,
        "p95_worker_duration_s": percentile(worker_durations, 95),
        "p95_queue_wait_s": percentile(queue_waits, 95),
        "avg_worker_duration_s": round(statistics.fmean(worker_durations), 6) if worker_durations else 0,
        "report_dir": report_dir,
        "sample_runs": results[:5],
    }
    report["passed"] = (
        report["success_rate"] >= 0.99
        and report["artifact_success_rate"] >= 0.99
        and report["task_final_status_consistency"]
        and report["unsafe_operation_blocked"]
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="Run isolated Agent platform stress checks.")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--report-dir", default="")
    args = parser.parse_args()

    iterations = max(1, args.iterations)
    report_dir = args.report_dir or os.path.join(tempfile.gettempdir(), "ragflow_agent_stress_reports")
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    scoped_db_module.SCOPED_DB_ROOT = os.path.join(report_dir, f"scoped_db_{args.mode}_{int(time.time())}")
    storage = FakeStorage()
    settings.STORAGE_IMPL = storage
    doc_write_module.REDIS_CONN = FakeRedisKV()

    started = time.perf_counter()
    results = []
    for index in range(iterations):
        try:
            results.append(run_iteration(index, storage))
        except Exception as exc:
            results.append(
                {
                    "run_id": f"stress-run-{index}",
                    "status": "failed",
                    "error": str(exc),
                    "queue_wait_s": 0,
                    "worker_duration_s": 0,
                    "artifact_count": 0,
                    "artifact_docs": [],
                }
            )
    elapsed = time.perf_counter() - started
    report = build_report(args.mode, iterations, results, elapsed, report_dir)
    report_path = os.path.join(report_dir, f"agent_stress_{args.mode}_{int(time.time())}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({**report, "report_path": report_path}, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
