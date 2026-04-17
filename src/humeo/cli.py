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
  humeo --long-to-shorts "https://youtube.com/watch?v=abc123" --provider openai
  humeo --long-to-shorts "https://youtube.com/watch?v=abc123" -o output
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
        default=Path(".humeo_work"),
        help="Working directory for intermediate files (default: ./.humeo_work)",
    )

    parser.add_argument(
        "--provider",
        choices=["gemini", "openai"],
        default="gemini",
        help="LLM provider for clip selection (default: gemini)",
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
        llm_provider=args.provider,
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
