"""CLI entry point for the Humeo pipeline."""

import argparse
import logging
import sys
from pathlib import Path

from humeo.config import PipelineConfig
from humeo.pipeline import run_pipeline


def setup_logging(verbose: bool = False):
    """Configure logging with a clean format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="humeo",
        description="Humeo - Automated podcast-to-shorts pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  humeo --long-to-shorts "https://youtube.com/watch?v=abc123"
  humeo --long-to-shorts "https://youtube.com/watch?v=abc123" --work-dir .humeo_work
  humeo --long-to-shorts "https://youtube.com/watch?v=abc123" --gemini-model gemini-2.0-flash
        """,
    )

    parser.add_argument(
        "--long-to-shorts",
        metavar="URL",
        required=True,
        help="YouTube video URL to process",
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output"),
        help="Output directory for final shorts (default: ./output)",
    )

    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Working directory for intermediate files. Default: per-video folder under the "
        "cache root (see docs/ENVIRONMENT.md). Use this to force e.g. ./.humeo_work.",
    )

    parser.add_argument(
        "--no-video-cache",
        action="store_true",
        help="Do not use per-video cache dirs; use ./.humeo_work unless --work-dir is set.",
    )

    parser.add_argument(
        "--cache-root",
        type=Path,
        default=None,
        help="Override cache root for manifests and per-video ingest (env: HUMEO_CACHE_ROOT).",
    )

    parser.add_argument(
        "--gemini-model",
        default=None,
        help="Gemini model id for clip selection (default: GEMINI_MODEL env; see humeo.config).",
    )

    parser.add_argument(
        "--force-clip-selection",
        action="store_true",
        help="Re-run clip-selection LLM even when clips.meta.json matches the transcript.",
    )

    parser.add_argument(
        "--gemini-vision-model",
        default=None,
        help="Gemini model for per-keyframe layout + bbox (default: GEMINI_VISION_MODEL env or --gemini-model).",
    )

    parser.add_argument(
        "--force-layout-vision",
        action="store_true",
        help="Re-run Gemini vision for layouts even when layout_vision.meta.json matches.",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    return parser


def main():
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    config = PipelineConfig(
        youtube_url=args.long_to_shorts,
        output_dir=args.output,
        work_dir=args.work_dir,
        use_video_cache=not args.no_video_cache,
        cache_root=args.cache_root,
        gemini_model=args.gemini_model,
        gemini_vision_model=args.gemini_vision_model,
        force_clip_selection=args.force_clip_selection,
        force_layout_vision=args.force_layout_vision,
    )

    try:
        outputs = run_pipeline(config)
        print(f"\nDone. {len(outputs)} shorts generated in: {config.output_dir}")
        for p in outputs:
            print(f"   -> {p}")
    except KeyboardInterrupt:
        print("\nPipeline interrupted.")
        sys.exit(1)
    except Exception as e:
        logging.getLogger(__name__).error("Pipeline failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
