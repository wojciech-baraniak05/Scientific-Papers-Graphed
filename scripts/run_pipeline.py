import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.populate import PipelineConfig, run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time population pipeline for Paper Citation Explorer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scope",
        default="popular",
        help="popular | field:ID | domain:ID (ID may be 22, fields/22, or full URL)",
    )
    parser.add_argument("--target-gb", type=float, default=5.0, help="stop near this DB size")
    parser.add_argument(
        "--max-papers", type=int, default=None,
        help="cap fully-ingested papers (smoke testing); default: no cap",
    )
    parser.add_argument(
        "--max-enrichment-ids", type=int, default=50000,
        help="cap referenced-paper enrichment; 0 disables Phase 3",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="works per page/batch (<=200)")
    parser.add_argument("--skip-reference-data", action="store_true", help="skip Phase 1")
    parser.add_argument("--skip-enrichment", action="store_true", help="skip Phase 3")
    args = parser.parse_args()

    cfg = PipelineConfig(
        scope=args.scope,
        target_gb=args.target_gb,
        max_papers=args.max_papers,
        max_enrichment_ids=args.max_enrichment_ids,
        batch_size=args.batch_size,
        skip_reference_data=args.skip_reference_data,
        skip_enrichment=args.skip_enrichment,
    )
    summary = run_pipeline(cfg)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
