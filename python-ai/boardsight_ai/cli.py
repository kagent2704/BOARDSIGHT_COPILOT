from __future__ import annotations

import argparse
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = CURRENT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from boardsight_ai.pipeline import run_pipeline, write_result
from boardsight_ai.providers.media import clip_video_fast
from boardsight_ai.storage import save_meeting_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the BoardSight AI pipeline.")
    parser.add_argument("--video", required=True, help="Absolute or relative path to a meeting video.")
    parser.add_argument("--output-dir", default="output", help="Directory for generated pipeline artifacts.")
    parser.add_argument(
        "--result-file",
        default="",
        help="Optional explicit JSON output path. Defaults to <output-dir>/boardsight_result.json",
    )
    parser.add_argument(
        "--meeting-db",
        default="",
        help="Optional explicit SQLite path for storing analysis metadata. Defaults to <output-dir>/../appdata/boardsight_meetings.db",
    )
    parser.add_argument("--start-seconds", type=float, default=None, help="Optional analysis start offset in seconds.")
    parser.add_argument("--end-seconds", type=float, default=None, help="Optional analysis end offset in seconds.")
    parser.add_argument(
        "--analysis-profile",
        default="",
        help="Optional analysis profile label for recorded-meeting runs. Legacy deep values are accepted, but production requests route to the lightweight BoardSight pipeline.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"Input video not found: {video_path}")
        return 1

    output_dir = Path(args.output_dir).resolve()
    analysis_input_path = video_path
    analysis_range = None
    if args.start_seconds is not None or args.end_seconds is not None:
        clipped_input_path = output_dir / "analysis_input.mp4"
        analysis_range = clip_video_fast(video_path, clipped_input_path, args.start_seconds, args.end_seconds)
        analysis_input_path = Path(str(analysis_range["output_path"])).resolve()
    result = run_pipeline(
        analysis_input_path,
        output_dir,
        analysis_range=analysis_range,
        analysis_profile=args.analysis_profile or None,
    )
    result_path = Path(args.result_file).resolve() if args.result_file else output_dir / "boardsight_result.json"
    write_result(result, result_path)
    default_db = output_dir.parent / "appdata" / "boardsight_meetings.db"
    meeting_db = Path(args.meeting_db).resolve() if args.meeting_db else default_db
    meeting_id = save_meeting_result(meeting_db, result, output_dir=output_dir, result_file=result_path)

    print(f"BoardSight AI pipeline completed: {result_path}")
    print(f"Stored analysis metadata in: {meeting_db} (meeting_id={meeting_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
