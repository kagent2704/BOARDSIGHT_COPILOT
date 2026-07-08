from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boardsight_ai.config import AppConfig, default_config
from boardsight_ai.evaluation import write_evaluation
from boardsight_ai.lightweight_pipeline import run_lightweight_pipeline
from boardsight_ai.models import PipelineResult
from boardsight_ai.reporting import write_structured_reports


def run_pipeline(
    video_path: Path,
    output_dir: Path,
    config: AppConfig | None = None,
    analysis_range: dict[str, float | None] | None = None,
    analysis_profile: str | None = None,
) -> PipelineResult:
    resolved_config = config or default_config(output_root=output_dir)
    return run_lightweight_pipeline(
        video_path,
        output_dir,
        resolved_config,
        analysis_range=analysis_range,
        requested_profile=analysis_profile,
    )


def write_result(result: PipelineResult, result_file: Path) -> Path:
    result_file.parent.mkdir(parents=True, exist_ok=True)
    report_files = write_structured_reports(result, result_file.parent)
    performance_report_path = write_evaluation(result, result_file.parent)
    payload: dict[str, Any] = result.to_dict()
    payload.setdefault("metadata", {})
    payload["metadata"]["report_files"] = report_files
    payload["metadata"]["performance_report_file"] = str(performance_report_path)
    result_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result_file
