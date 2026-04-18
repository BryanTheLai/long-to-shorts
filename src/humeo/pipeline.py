"""End-to-end product pipeline."""

import json
import logging
from pathlib import Path

from humeo_mcp.primitives.ingest import extract_keyframes
from humeo_mcp.schemas import LayoutInstruction, LayoutKind, Scene

from humeo.clip_selection_cache import cache_valid, load_meta, transcript_fingerprint, write_artifacts
from humeo.clip_selector import load_clips, save_clips, select_clips
from humeo.config import PipelineConfig
from humeo.cutter import generate_srt
from humeo.ingest import download_video, extract_audio, transcribe_whisperx
from humeo.layout_vision import run_layout_vision_stage
from humeo.render_window import clip_for_render
from humeo.reframe_ffmpeg import reframe_clip_ffmpeg
from humeo.video_cache import (
    extract_youtube_video_id,
    ingest_complete,
    read_youtube_info_json,
    resolve_work_directory,
    upsert_manifest_from_info,
)

logger = logging.getLogger(__name__)


def _ensure_work_dir(config: PipelineConfig) -> None:
    """Resolve ``config.work_dir`` when unset (per-video cache) or ensure it exists."""
    if config.work_dir is not None:
        return
    config.work_dir = resolve_work_directory(
        youtube_url=config.youtube_url,
        explicit_work_dir=None,
        use_video_cache=config.use_video_cache,
        cache_root=config.cache_root,
    )


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

    _ensure_work_dir(config)
    assert config.work_dir is not None

    # ------------------------------------------------------------------
    # Stage 1: Ingest
    # ------------------------------------------------------------------
    logger.info("--- STAGE 1: INGESTION ---")

    source_video = config.work_dir / "source.mp4"
    transcript_path = config.work_dir / "transcript.json"

    if ingest_complete(config.work_dir):
        logger.info("Cached ingest found for this URL (reusing source + transcript).")
    elif source_video.exists():
        logger.info("Source video already downloaded, skipping download.")
    else:
        source_video = download_video(config.youtube_url, config.work_dir)

    if transcript_path.exists():
        logger.info("Transcript already exists, loading.")
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = json.load(f)
    else:
        audio_path = extract_audio(source_video, config.work_dir)
        transcript = transcribe_whisperx(audio_path, config.work_dir)

    vid = extract_youtube_video_id(config.youtube_url)
    info = read_youtube_info_json(config.work_dir)
    if not info and vid:
        info = {"id": vid, "webpage_url": config.youtube_url}
    if info:
        upsert_manifest_from_info(
            work_dir=config.work_dir,
            youtube_url=config.youtube_url,
            info=info,
            cache_root=config.cache_root,
        )

    # ------------------------------------------------------------------
    # Stage 2: Clip Selection
    # ------------------------------------------------------------------
    logger.info("--- STAGE 2: CLIP SELECTION ---")

    clips_path = config.work_dir / "clips.json"
    fp = transcript_fingerprint(transcript)
    meta = load_meta(config.work_dir)
    cache_hit = (
        clips_path.is_file()
        and not config.force_clip_selection
        and meta is not None
        and cache_valid(meta, fp, config)
    )

    if cache_hit:
        clips = load_clips(clips_path)
        logger.info("Clip selection cache hit (transcript + provider/model unchanged); skipping LLM.")
    else:
        clips, raw = select_clips(transcript, gemini_model=config.gemini_model)
        save_clips(clips, clips_path)
        write_artifacts(
            config.work_dir,
            transcript=transcript,
            config=config,
            raw_response=raw,
        )

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
    clip_scenes: list[Scene] = []
    for clip in clips:
        rw = clip_for_render(clip)
        clip_scenes.append(
            Scene(scene_id=clip.clip_id, start_time=rw.start_time_sec, end_time=rw.end_time_sec)
        )
    clip_scenes = extract_keyframes(str(source_video), clip_scenes, str(keyframes_dir))
    layout_instructions = run_layout_vision_stage(
        config.work_dir,
        clip_scenes,
        transcript_fp=fp,
        clips_path=clips_path,
        config=config,
    )

    # ------------------------------------------------------------------
    # Stage 4: Render
    # ------------------------------------------------------------------
    logger.info("--- STAGE 4: RENDER ---")

    final_outputs: list[Path] = []
    subtitles_dir = config.work_dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)

    for clip in clips:
        instr = layout_instructions.get(clip.clip_id)
        if instr is None:
            hint = clip.layout_hint or LayoutKind.SIT_CENTER
            instr = LayoutInstruction(clip_id=clip.clip_id, layout=hint)
        clip.layout = instr.layout
        rclip = clip_for_render(clip)
        srt_path = generate_srt(rclip, transcript, subtitles_dir)
        final_path = config.output_dir / f"short_{clip.clip_id}.mp4"
        if final_path.exists():
            logger.info("Clip %s already rendered, skipping.", clip.clip_id)
            final_outputs.append(final_path)
            continue

        reframe_clip_ffmpeg(
            input_path=source_video,
            output_path=final_path,
            clip=rclip,
            layout_instruction=instr,
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
