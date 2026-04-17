"""End-to-end product pipeline."""

import json
import logging
from pathlib import Path

from humeo_mcp.primitives.classify import classify_scenes_heuristic
from humeo_mcp.primitives.ingest import extract_keyframes
from humeo_mcp.schemas import Scene

from humeo.clip_selector import load_clips, save_clips, select_clips
from humeo.config import PipelineConfig
from humeo.cutter import generate_srt
from humeo.ingest import download_video, extract_audio, transcribe_whisperx
from humeo.reframe_ffmpeg import reframe_clip_ffmpeg

logger = logging.getLogger(__name__)


def run_pipeline(config: PipelineConfig) -> list[Path]:
    """
    Execute the full podcast-to-shorts pipeline.

    Args:
        config: Pipeline configuration.

    Returns:
        List of paths to the final short-form MP4 files.
    """
    logger.info("=" * 60)
    logger.info("HUMEO PIPELINE START")
    logger.info("URL: %s", config.youtube_url)
    logger.info("Output: %s", config.output_dir)
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Stage 1: Ingest
    # ------------------------------------------------------------------
    logger.info("--- STAGE 1: INGESTION ---")

    source_video = config.work_dir / "source.mp4"
    transcript_path = config.work_dir / "transcript.json"

    if source_video.exists():
        logger.info("Source video already downloaded, skipping.")
    else:
        source_video = download_video(config.youtube_url, config.work_dir)

    if transcript_path.exists():
        logger.info("Transcript already exists, loading.")
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = json.load(f)
    else:
        audio_path = extract_audio(source_video, config.work_dir)
        transcript = transcribe_whisperx(audio_path, config.work_dir)

    # ------------------------------------------------------------------
    # Stage 2: Clip Selection
    # ------------------------------------------------------------------
    logger.info("--- STAGE 2: CLIP SELECTION ---")

    clips_path = config.work_dir / "clips.json"

    if clips_path.exists():
        logger.info("Clips already selected, loading.")
        clips = load_clips(clips_path)
    else:
        clips = select_clips(transcript, provider=config.llm_provider)
        save_clips(clips, clips_path)

    logger.info("Selected %d clips:", len(clips))
    for clip in clips:
        logger.info(
            "  [%s] %.1fs-%.1fs (%.1fs) score=%.2f - %s",
            clip.clip_id,
            clip.start_time_sec,
            clip.end_time_sec,
            clip.duration_sec,
            clip.virality_score,
            clip.topic,
        )

    # ------------------------------------------------------------------
    # Stage 3: Clip layouts
    # ------------------------------------------------------------------
    logger.info("--- STAGE 3: CLIP LAYOUTS ---")

    keyframes_dir = config.work_dir / "keyframes"
    clip_scenes = [
        Scene(
            scene_id=clip.clip_id,
            start_time=clip.start_time_sec,
            end_time=clip.end_time_sec,
        )
        for clip in clips
    ]
    clip_scenes = extract_keyframes(str(source_video), clip_scenes, str(keyframes_dir))
    classifications = classify_scenes_heuristic(clip_scenes)
    layout_by_clip = {item.scene_id: item.layout for item in classifications}

    # ------------------------------------------------------------------
    # Stage 4: Render
    # ------------------------------------------------------------------
    logger.info("--- STAGE 4: RENDER ---")

    final_outputs: list[Path] = []
    subtitles_dir = config.work_dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)

    for clip in clips:
        clip.layout = layout_by_clip.get(clip.clip_id)
        srt_path = generate_srt(clip, subtitles_dir)
        final_path = config.output_dir / f"short_{clip.clip_id}.mp4"
        if final_path.exists():
            logger.info("Clip %s already rendered, skipping.", clip.clip_id)
            final_outputs.append(final_path)
            continue

        reframe_clip_ffmpeg(
            input_path=source_video,
            output_path=final_path,
            clip=clip,
            subtitle_path=srt_path,
            title_text=clip.suggested_overlay_title,
        )
        final_outputs.append(final_path)

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE - %d shorts generated:", len(final_outputs))
    for p in final_outputs:
        logger.info("  -> %s", p)
    logger.info("=" * 60)

    return final_outputs
