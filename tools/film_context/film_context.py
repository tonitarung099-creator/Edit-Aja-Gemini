#!/usr/bin/env python3
"""Optional local Film Context capability for Update P5 Edit Aja.

Purpose: let an AI agent search a long movie without sending the whole movie to
an API. The base index is deliberately dependency-light: FFmpeg/FFprobe +
SQLite + subtitle text. Frames are generated only on demand for a small set of
candidate scenes.

The stable JSON tool surface is intentionally separate from AI Edit JSON:
Film Context describes/searches source media; AI Edit JSON edits the timeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FORMAT = "update-p5-film-context"
VERSION = 1
SCENE_TIME_RE = re.compile(r"\bpts_time:(-?\d+(?:\.\d+)?)")
TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
SRT_BLOCK_RE = re.compile(r"\r?\n\s*\r?\n")

# Small, recap-oriented visual vocabulary. OpenCLIP compares one representative
# scene frame against the English labels once during indexing; both English and
# Indonesian aliases are persisted so normal movie_search stays dependency-light.
VISUAL_LABELS = [
    ("a person", "orang"), ("a man", "pria"), ("a woman", "wanita"),
    ("two people talking", "dua orang berbicara"), ("a group of people", "sekelompok orang"),
    ("a close up face", "wajah close up"), ("a person crying", "orang menangis"),
    ("a person smiling", "orang tersenyum"), ("a person angry", "orang marah"),
    ("a person afraid", "orang ketakutan"), ("a person sleeping", "orang tidur"),
    ("a person lying down", "orang berbaring"), ("a person walking", "orang berjalan"),
    ("a person running", "orang berlari"), ("a person entering a room", "orang masuk ruangan"),
    ("a person leaving", "orang pergi"), ("a person opening a door", "orang membuka pintu"),
    ("a person looking at something", "orang melihat sesuatu"), ("a person holding an object", "orang memegang benda"),
    ("a person using a phone", "orang menggunakan telepon"), ("a person reading", "orang membaca"),
    ("a person driving", "orang mengemudi"), ("a car", "mobil"), ("a motorcycle", "sepeda motor"),
    ("a road", "jalan"), ("a car crash", "kecelakaan mobil"), ("an explosion", "ledakan"),
    ("a fire", "api kebakaran"), ("a gun", "pistol senjata"), ("a person shooting", "orang menembak"),
    ("a fight", "perkelahian"), ("a chase", "pengejaran"), ("a dead body", "mayat"),
    ("blood or injury", "darah luka"), ("a hospital", "rumah sakit"), ("a police scene", "polisi"),
    ("a house exterior", "luar rumah"), ("inside a house", "dalam rumah"), ("a bedroom", "kamar tidur"),
    ("a living room", "ruang tamu"), ("a kitchen", "dapur"), ("an office", "kantor"),
    ("a school", "sekolah"), ("a restaurant", "restoran"), ("a shop or store", "toko"),
    ("a street at night", "jalan malam"), ("a city", "kota"), ("a forest", "hutan"),
    ("a field", "lapangan"), ("a beach or sea", "pantai laut"), ("a mountain", "gunung"),
    ("a prison", "penjara"), ("a courtroom", "ruang sidang"), ("a funeral", "pemakaman"),
    ("a wedding", "pernikahan"), ("a party", "pesta"), ("a family scene", "adegan keluarga"),
    ("a romantic scene", "adegan romantis"), ("a hug", "pelukan"), ("a kiss", "ciuman"),
    ("food on a table", "makanan di meja"), ("money", "uang"), ("a document or letter", "dokumen surat"),
    ("a computer screen", "layar komputer"), ("a photograph", "foto"), ("a weapon", "senjata"),
    ("daylight exterior", "luar siang"), ("night exterior", "luar malam"),
    ("dark interior", "ruangan gelap"), ("bright interior", "ruangan terang"),
]


class FilmContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class Subtitle:
    start: float
    end: float
    text: str


def _binary(name: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise FilmContextError(f"{name} was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise FilmContextError(f"Could not execute {args[0]}: {exc}") from exc


def _parse_clock(value: str) -> float:
    match = re.fullmatch(r"\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = match.groups()
    ms = int(millis.ljust(3, "0")[:3])
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + ms / 1000.0


def parse_srt(text: str) -> list[Subtitle]:
    subtitles: list[Subtitle] = []
    for block in SRT_BLOCK_RE.split(text.strip()):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        timing = lines[timing_index].split("-->", 1)
        if len(timing) != 2:
            continue
        try:
            start = _parse_clock(timing[0])
            end = _parse_clock(timing[1])
        except ValueError:
            continue
        if end <= start:
            continue
        body = " ".join(x.strip() for x in lines[timing_index + 1 :] if x.strip())
        body = re.sub(r"<[^>]+>", "", body)
        body = re.sub(r"\{\\[^}]+\}", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            subtitles.append(Subtitle(start=start, end=end, text=body))
    return subtitles


def parse_scene_times(text: str) -> list[float]:
    times: list[float] = []
    for line in text.splitlines():
        if "showinfo" not in line:
            continue
        match = SCENE_TIME_RE.search(line)
        if match:
            value = max(0.0, float(match.group(1)))
            if not times or abs(value - times[-1]) > 1e-4:
                times.append(value)
    return times


def scene_segments(cuts: Iterable[float], duration: float) -> list[dict[str, float | int]]:
    if duration <= 0:
        return []
    boundaries = [0.0] + [x for x in sorted(set(float(v) for v in cuts)) if 0 < x < duration] + [float(duration)]
    result: list[dict[str, float | int]] = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        if end <= start:
            continue
        result.append(
            {
                "scene_id": index,
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "duration_seconds": round(end - start, 6),
            }
        )
    return result


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def scene_dialogue(scene: dict[str, Any], subtitles: Iterable[Subtitle]) -> tuple[str, int]:
    start = float(scene["start_seconds"])
    end = float(scene["end_seconds"])
    selected = [s.text for s in subtitles if _overlap(start, end, s.start, s.end) > 0]
    return " ".join(selected).strip(), len(selected)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token) > 1]


def _bm25(
    query: list[str],
    document: list[str],
    *,
    doc_freq: Counter[str],
    doc_count: int,
    avg_len: float,
    k1: float = 1.3,
    b: float = 0.75,
) -> float:
    if not query or not document or doc_count <= 0:
        return 0.0
    counts = Counter(document)
    length = len(document)
    score = 0.0
    for term in set(query):
        tf = counts.get(term, 0)
        if not tf:
            continue
        df = doc_freq.get(term, 0)
        idf = math.log(1.0 + (doc_count - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1.0 - b + b * (length / max(avg_len, 1e-9)))
        score += idf * (tf * (k1 + 1.0)) / denom
    return score


def _normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    best = max(values)
    if best <= 0:
        return [0.0 for _ in values]
    return [v / best for v in values]


def compact_text(text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"[:max_chars]
    return text[: max_chars - 1].rstrip() + "…"


def file_fingerprint(path: Path, sample_bytes: int = 1024 * 1024) -> str:
    stat = path.stat()
    h = hashlib.sha256()
    h.update(str(path.resolve()).encode("utf-8", errors="surrogatepass"))
    h.update(str(stat.st_size).encode("ascii"))
    with path.open("rb") as fh:
        h.update(fh.read(sample_bytes))
        if stat.st_size > sample_bytes:
            fh.seek(max(0, stat.st_size - sample_bytes))
            h.update(fh.read(sample_bytes))
    return h.hexdigest()[:24]


def probe_duration(media: Path, ffprobe: str) -> float:
    proc = _run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(media)])
    if proc.returncode != 0:
        raise FilmContextError(proc.stderr.strip() or "ffprobe failed")
    try:
        duration = float(proc.stdout.strip())
    except ValueError as exc:
        raise FilmContextError("ffprobe returned an invalid duration") from exc
    if duration <= 0:
        raise FilmContextError("media duration is not positive")
    return duration


def detect_scene_cuts(media: Path, ffmpeg: str, threshold: float = 0.35) -> list[float]:
    if not 0 < threshold < 1:
        raise FilmContextError("scene threshold must be between 0 and 1")
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(media),
            "-vf",
            f"select='gt(scene,{threshold:g})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode not in (0, 255):
        raise FilmContextError(proc.stderr.strip() or "FFmpeg scene detection failed")
    return parse_scene_times(proc.stderr)


def _connect(index_dir: Path) -> sqlite3.Connection:
    db = index_dir / "movie.db"
    if not db.exists():
        raise FilmContextError(f"Film Context index not found: {db}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scene_visual (
            scene_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL,
            pretrained TEXT NOT NULL,
            frame_time REAL NOT NULL,
            frame_path TEXT NOT NULL,
            tags_text TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            FOREIGN KEY(scene_id) REFERENCES scenes(scene_id)
        )
        """
    )
    return conn


def write_index(
    index_dir: Path,
    *,
    media: Path,
    duration: float,
    threshold: float,
    scenes: list[dict[str, Any]],
    subtitles: list[Subtitle],
    fingerprint: str,
) -> dict[str, Any]:
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "movie.db"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE scenes (
                scene_id INTEGER PRIMARY KEY,
                start_seconds REAL NOT NULL,
                end_seconds REAL NOT NULL,
                duration_seconds REAL NOT NULL,
                dialogue TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                subtitle_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE subtitles (
                subtitle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_seconds REAL NOT NULL,
                end_seconds REAL NOT NULL,
                text TEXT NOT NULL
            );
            CREATE INDEX subtitles_time ON subtitles(start_seconds, end_seconds);
            CREATE TABLE scene_visual (
                scene_id INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                pretrained TEXT NOT NULL,
                frame_time REAL NOT NULL,
                frame_path TEXT NOT NULL,
                tags_text TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                FOREIGN KEY(scene_id) REFERENCES scenes(scene_id)
            );
            """
        )
        meta = {
            "format": FORMAT,
            "version": str(VERSION),
            "media_path": str(media.resolve()),
            "fingerprint": fingerprint,
            "duration_seconds": repr(float(duration)),
            "scene_threshold": repr(float(threshold)),
        }
        conn.executemany("INSERT INTO meta(key,value) VALUES (?,?)", meta.items())
        for subtitle in subtitles:
            conn.execute(
                "INSERT INTO subtitles(start_seconds,end_seconds,text) VALUES (?,?,?)",
                (subtitle.start, subtitle.end, subtitle.text),
            )
        for scene in scenes:
            dialogue, subtitle_count = scene_dialogue(scene, subtitles)
            conn.execute(
                "INSERT INTO scenes(scene_id,start_seconds,end_seconds,duration_seconds,dialogue,notes,subtitle_count) VALUES (?,?,?,?,?,?,?)",
                (
                    int(scene["scene_id"]),
                    float(scene["start_seconds"]),
                    float(scene["end_seconds"]),
                    float(scene["duration_seconds"]),
                    dialogue,
                    "",
                    subtitle_count,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "media_path": str(media.resolve()),
        "fingerprint": fingerprint,
        "duration_seconds": round(float(duration), 6),
        "scene_threshold": threshold,
        "scene_count": len(scenes),
        "subtitle_count": len(subtitles),
        "storage": {"database": "movie.db", "keyframe_cache": "keyframes/"},
        "privacy": {
            "base_index_local_only": True,
            "api_upload_required": False,
            "keyframes_generated_on_demand": True,
        },
    }
    (index_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_index(
    media: Path,
    *,
    srt: Path | None,
    index_dir: Path,
    ffmpeg: str,
    ffprobe: str,
    threshold: float,
) -> dict[str, Any]:
    duration = probe_duration(media, ffprobe)
    cuts = detect_scene_cuts(media, ffmpeg, threshold)
    scenes = scene_segments(cuts, duration)
    subtitles: list[Subtitle] = []
    if srt:
        subtitles = parse_srt(srt.read_text(encoding="utf-8-sig", errors="replace"))
    return write_index(
        index_dir,
        media=media,
        duration=duration,
        threshold=threshold,
        scenes=scenes,
        subtitles=subtitles,
        fingerprint=file_fingerprint(media),
    )


def status(index_dir: Path) -> dict[str, Any]:
    conn = _connect(index_dir)
    try:
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM meta")}
        scene_count = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        subtitle_count = conn.execute("SELECT COUNT(*) FROM subtitles").fetchone()[0]
        note_count = conn.execute("SELECT COUNT(*) FROM scenes WHERE length(trim(notes)) > 0").fetchone()[0]
        visual_count = conn.execute("SELECT COUNT(*) FROM scene_visual").fetchone()[0]
        visual_row = conn.execute("SELECT model,pretrained FROM scene_visual LIMIT 1").fetchone()
    finally:
        conn.close()
    return {
        "ok": True,
        "format": meta.get("format", FORMAT),
        "version": int(meta.get("version", VERSION)),
        "index_path": str(index_dir.resolve()),
        "media_path": meta.get("media_path"),
        "fingerprint": meta.get("fingerprint"),
        "duration_seconds": float(meta.get("duration_seconds", 0.0)),
        "scene_count": int(scene_count),
        "subtitle_count": int(subtitle_count),
        "annotated_scene_count": int(note_count),
        "visual_scene_count": int(visual_count),
        "visual_ready": bool(visual_count),
        "visual_model": visual_row["model"] if visual_row else None,
        "visual_pretrained": visual_row["pretrained"] if visual_row else None,
        "api_required": False,
    }


def _load_scene_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT s.*, COALESCE(v.tags_text, '') AS visual_tags
            FROM scenes s
            LEFT JOIN scene_visual v ON v.scene_id = s.scene_id
            ORDER BY s.scene_id
            """
        )
    ]


def search_index(
    index_dir: Path,
    query: str,
    *,
    top_k: int = 5,
    near_scene: int | None = None,
    max_text_chars: int = 420,
) -> dict[str, Any]:
    query_tokens = tokenize(query)
    if not query_tokens:
        raise FilmContextError("query must contain searchable text")
    conn = _connect(index_dir)
    try:
        rows = _load_scene_rows(conn)
    finally:
        conn.close()
    docs = [tokenize(f"{row['dialogue']} {row['notes']} {row.get('visual_tags', '')}") for row in rows]
    doc_freq: Counter[str] = Counter()
    for doc in docs:
        doc_freq.update(set(doc))
    avg_len = sum(len(doc) for doc in docs) / max(len(docs), 1)
    raw = [_bm25(query_tokens, doc, doc_freq=doc_freq, doc_count=len(docs), avg_len=avg_len) for doc in docs]
    normalized = _normalize_scores(raw)

    scored: list[tuple[float, float, dict[str, Any]]] = []
    for row, semantic in zip(rows, normalized):
        continuity = 0.0
        if near_scene is not None:
            distance = abs(int(row["scene_id"]) - int(near_scene))
            continuity = 1.0 / (1.0 + distance / 8.0)
        score = semantic if near_scene is None else semantic * 0.85 + continuity * 0.15
        scored.append((score, semantic, row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    results = []
    for score, semantic, row in scored[: max(1, min(int(top_k), 50))]:
        results.append(
            {
                "scene_id": int(row["scene_id"]),
                "start_seconds": round(float(row["start_seconds"]), 6),
                "end_seconds": round(float(row["end_seconds"]), 6),
                "duration_seconds": round(float(row["duration_seconds"]), 6),
                "score": round(float(score), 4),
                "text_score": round(float(semantic), 4),
                "dialogue": compact_text(row["dialogue"], max_text_chars),
                "notes": compact_text(row["notes"], max_text_chars),
                "visual_tags": compact_text(row.get("visual_tags", ""), max_text_chars),
            }
        )
    return {
        "ok": True,
        "query": query,
        "top_k": len(results),
        "near_scene": near_scene,
        "retrieval": "local-bm25-dialogue-notes",
        "results": results,
        "api_used": False,
    }


def get_scene(index_dir: Path, scene_id: int, *, max_text_chars: int = 2000) -> dict[str, Any]:
    conn = _connect(index_dir)
    try:
        row = conn.execute(
            """
            SELECT s.*, COALESCE(v.tags_text, '') AS visual_tags
            FROM scenes s LEFT JOIN scene_visual v ON v.scene_id=s.scene_id
            WHERE s.scene_id=?
            """,
            (scene_id,),
        ).fetchone()
        if row is None:
            raise FilmContextError(f"Unknown scene_id: {scene_id}")
        scene = dict(row)
        subtitles = [
            dict(item)
            for item in conn.execute(
                "SELECT start_seconds,end_seconds,text FROM subtitles WHERE end_seconds > ? AND start_seconds < ? ORDER BY start_seconds",
                (scene["start_seconds"], scene["end_seconds"]),
            )
        ]
    finally:
        conn.close()
    return {
        "ok": True,
        "scene": {
            "scene_id": int(scene["scene_id"]),
            "start_seconds": round(float(scene["start_seconds"]), 6),
            "end_seconds": round(float(scene["end_seconds"]), 6),
            "duration_seconds": round(float(scene["duration_seconds"]), 6),
            "dialogue": compact_text(scene["dialogue"], max_text_chars),
            "notes": compact_text(scene["notes"], max_text_chars),
            "subtitle_count": int(scene["subtitle_count"]),
            "visual_tags": compact_text(scene.get("visual_tags", ""), max_text_chars),
        },
        "subtitles": [
            {
                "start_seconds": round(float(item["start_seconds"]), 6),
                "end_seconds": round(float(item["end_seconds"]), 6),
                "text": compact_text(str(item["text"]), max_text_chars),
            }
            for item in subtitles
        ],
        "api_used": False,
    }


def get_context(index_dir: Path, scene_id: int, *, radius: int = 2, max_text_chars: int = 500) -> dict[str, Any]:
    radius = max(0, min(int(radius), 10))
    conn = _connect(index_dir)
    try:
        row = conn.execute("SELECT scene_id FROM scenes WHERE scene_id=?", (scene_id,)).fetchone()
        if row is None:
            raise FilmContextError(f"Unknown scene_id: {scene_id}")
        rows = [
            dict(item)
            for item in conn.execute(
                """
                SELECT s.*, COALESCE(v.tags_text, '') AS visual_tags
                FROM scenes s LEFT JOIN scene_visual v ON v.scene_id=s.scene_id
                WHERE s.scene_id BETWEEN ? AND ? ORDER BY s.scene_id
                """,
                (scene_id - radius, scene_id + radius),
            )
        ]
    finally:
        conn.close()
    return {
        "ok": True,
        "focus_scene": scene_id,
        "radius": radius,
        "scenes": [
            {
                "scene_id": int(row["scene_id"]),
                "focus": int(row["scene_id"]) == scene_id,
                "start_seconds": round(float(row["start_seconds"]), 6),
                "end_seconds": round(float(row["end_seconds"]), 6),
                "dialogue": compact_text(row["dialogue"], max_text_chars),
                "notes": compact_text(row["notes"], max_text_chars),
                "visual_tags": compact_text(row.get("visual_tags", ""), max_text_chars),
            }
            for row in rows
        ],
        "api_used": False,
    }


def annotate_scene(index_dir: Path, scene_id: int, notes: str) -> dict[str, Any]:
    conn = _connect(index_dir)
    try:
        cur = conn.execute("UPDATE scenes SET notes=? WHERE scene_id=?", (notes.strip(), scene_id))
        if cur.rowcount != 1:
            raise FilmContextError(f"Unknown scene_id: {scene_id}")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "scene_id": scene_id, "notes": notes.strip(), "api_used": False}


def _safe_keyframe_time(start: float, end: float, index: int, count: int) -> float:
    duration = max(0.0, end - start)
    fraction = (index + 1) / (count + 1)
    return start + duration * fraction


def get_keyframes(
    index_dir: Path,
    scene_ids: list[int],
    *,
    count_per_scene: int = 2,
    ffmpeg: str,
    width: int = 768,
) -> dict[str, Any]:
    count_per_scene = max(1, min(int(count_per_scene), 4))
    info = status(index_dir)
    media = Path(str(info["media_path"]))
    if not media.exists():
        raise FilmContextError(f"Indexed media is not available: {media}")
    cache_dir = index_dir / "keyframes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for scene_id in scene_ids[:10]:
        scene = get_scene(index_dir, int(scene_id))["scene"]
        frames = []
        for i in range(count_per_scene):
            at = _safe_keyframe_time(float(scene["start_seconds"]), float(scene["end_seconds"]), i, count_per_scene)
            path = cache_dir / f"scene-{scene_id:05d}-{i + 1}.jpg"
            if not path.exists():
                proc = _run(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        f"{at:.6f}",
                        "-i",
                        str(media),
                        "-frames:v",
                        "1",
                        "-vf",
                        f"scale='min({width},iw)':-2",
                        "-q:v",
                        "3",
                        "-y",
                        str(path),
                    ]
                )
                if proc.returncode != 0:
                    raise FilmContextError(proc.stderr.strip() or f"Could not extract keyframe for scene {scene_id}")
            frames.append({"time_seconds": round(at, 6), "path": str(path.resolve())})
        output.append({"scene_id": int(scene_id), "frames": frames})
    return {
        "ok": True,
        "media_path": str(media.resolve()),
        "count_per_scene": count_per_scene,
        "scenes": output,
        "generated_on_demand": True,
        "api_used": False,
    }



def _load_openclip_backend(model_name: str, pretrained: str, device: str):
    try:
        import open_clip  # type: ignore
        import torch  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise FilmContextError(
            "Visual semantic indexing is optional. Install open_clip_torch, torch and Pillow first."
        ) from exc

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
        tokenizer = open_clip.get_tokenizer(model_name)
    except Exception as exc:
        raise FilmContextError(f"Could not load OpenCLIP model {model_name}/{pretrained}: {exc}") from exc
    model = model.to(device)
    model.eval()
    return open_clip, torch, Image, model, preprocess, tokenizer, device


def _extract_visual_midframe(media: Path, target: Path, at: float, ffmpeg: str, width: int) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{at:.6f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-vf",
            f"scale='min({width},iw)':-2",
            "-q:v",
            "3",
            "-y",
            str(target),
        ]
    )
    if proc.returncode != 0:
        raise FilmContextError(proc.stderr.strip() or f"Could not extract visual frame at {at:.3f}s")


def build_visual_semantic_tags(
    index_dir: Path,
    *,
    ffmpeg: str,
    model_name: str = "ViT-B-32",
    pretrained: str = "laion2b_s34b_b79k",
    device: str = "auto",
    batch_size: int = 8,
    tags_per_scene: int = 8,
    width: int = 512,
    force: bool = False,
) -> dict[str, Any]:
    """Build optional local semantic visual tags once, then keep normal search light.

    The OpenCLIP model is needed only for this indexing command. movie_search
    later reads persisted bilingual tags from SQLite and does not import torch.
    """
    info = status(index_dir)
    media = Path(str(info["media_path"]))
    if not media.exists():
        raise FilmContextError(f"Indexed media is not available: {media}")

    _, torch, Image, model, preprocess, tokenizer, resolved_device = _load_openclip_backend(
        model_name, pretrained, device
    )
    prompts = [f"a movie scene showing {english}" for english, _ in VISUAL_LABELS]
    with torch.no_grad():
        text_tokens = tokenizer(prompts).to(resolved_device)
        text_features = model.encode_text(text_tokens)
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)

    conn = _connect(index_dir)
    try:
        rows = _load_scene_rows(conn)
        if force:
            conn.execute("DELETE FROM scene_visual")
            conn.commit()
        existing = {
            int(row["scene_id"])
            for row in conn.execute(
                "SELECT scene_id FROM scene_visual WHERE model=? AND pretrained=?",
                (model_name, pretrained),
            )
        }

        pending: list[tuple[dict[str, Any], Path, float]] = []
        cache_dir = index_dir / "visual-keyframes"
        for row in rows:
            scene_id = int(row["scene_id"])
            if scene_id in existing and not force:
                continue
            at = _safe_keyframe_time(float(row["start_seconds"]), float(row["end_seconds"]), 0, 1)
            frame_path = cache_dir / f"scene-{scene_id:05d}.jpg"
            _extract_visual_midframe(media, frame_path, at, ffmpeg, width)
            pending.append((row, frame_path, at))

        batch_size = max(1, min(int(batch_size), 64))
        tags_per_scene = max(1, min(int(tags_per_scene), 20))
        indexed = 0
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset : offset + batch_size]
            tensors = []
            for _, frame_path, _ in batch:
                with Image.open(frame_path) as image:
                    tensors.append(preprocess(image.convert("RGB")))
            if not tensors:
                continue
            images = torch.stack(tensors).to(resolved_device)
            with torch.no_grad():
                image_features = model.encode_image(images)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                similarities = image_features @ text_features.T

            for item_index, (row, frame_path, at) in enumerate(batch):
                values, indices = similarities[item_index].topk(min(tags_per_scene, len(VISUAL_LABELS)))
                tags = []
                tags_text_parts = []
                for score, label_index in zip(values.detach().cpu().tolist(), indices.detach().cpu().tolist()):
                    english, indonesian = VISUAL_LABELS[int(label_index)]
                    tags.append(
                        {
                            "en": english,
                            "id": indonesian,
                            "score": round(float(score), 4),
                        }
                    )
                    tags_text_parts.extend([english, indonesian])
                tags_text = " ; ".join(tags_text_parts)
                conn.execute(
                    """
                    INSERT INTO scene_visual(scene_id,model,pretrained,frame_time,frame_path,tags_text,tags_json)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(scene_id) DO UPDATE SET
                        model=excluded.model,
                        pretrained=excluded.pretrained,
                        frame_time=excluded.frame_time,
                        frame_path=excluded.frame_path,
                        tags_text=excluded.tags_text,
                        tags_json=excluded.tags_json
                    """,
                    (
                        int(row["scene_id"]),
                        model_name,
                        pretrained,
                        float(at),
                        str(frame_path.resolve()),
                        tags_text,
                        json.dumps(tags, ensure_ascii=False),
                    ),
                )
                indexed += 1
            conn.commit()
    finally:
        conn.close()

    final = status(index_dir)
    return {
        "ok": True,
        "backend": "openclip-semantic-tags",
        "model": model_name,
        "pretrained": pretrained,
        "device": resolved_device,
        "indexed_now": indexed,
        "visual_scene_count": final["visual_scene_count"],
        "scene_count": final["scene_count"],
        "tags_per_scene": tags_per_scene,
        "search_after_index": "lightweight-bm25-over-dialogue-notes-bilingual-visual-tags",
        "api_used": False,
    }


def tool_catalog() -> dict[str, Any]:
    return {
        "format": "update-p5-film-context-tools",
        "version": 1,
        "description": "Local movie retrieval tools. They never edit the timeline and never call an API.",
        "tools": [
            {
                "name": "movie_context_status",
                "description": "Inspect the active local Film Context index.",
                "required": [],
            },
            {
                "name": "movie_search",
                "description": "Search local scene dialogue/notes plus optional persisted visual semantic tags and return a small ranked candidate list.",
                "required": ["query"],
            },
            {
                "name": "movie_get_scene",
                "description": "Read one scene's timestamp and subtitle/dialogue context.",
                "required": ["scene_id"],
            },
            {
                "name": "movie_get_context",
                "description": "Read neighboring scenes around one candidate without reading the whole movie.",
                "required": ["scene_id"],
            },
            {
                "name": "movie_get_keyframes",
                "description": "Generate a few local JPEG keyframes only for requested candidate scenes.",
                "required": ["scene_ids"],
            },
        ],
    }


def invoke_tool(index_dir: Path, tool: str, arguments: dict[str, Any], *, ffmpeg: str | None = None) -> dict[str, Any]:
    if tool == "movie_context_status":
        return status(index_dir)
    if tool == "movie_search":
        return search_index(
            index_dir,
            str(arguments.get("query", "")),
            top_k=int(arguments.get("top_k", 5)),
            near_scene=int(arguments["near_scene"]) if arguments.get("near_scene") is not None else None,
            max_text_chars=int(arguments.get("max_text_chars", 420)),
        )
    if tool == "movie_get_scene":
        return get_scene(index_dir, int(arguments["scene_id"]), max_text_chars=int(arguments.get("max_text_chars", 2000)))
    if tool == "movie_get_context":
        return get_context(
            index_dir,
            int(arguments["scene_id"]),
            radius=int(arguments.get("radius", 2)),
            max_text_chars=int(arguments.get("max_text_chars", 500)),
        )
    if tool == "movie_get_keyframes":
        ids = arguments.get("scene_ids")
        if not isinstance(ids, list) or not ids:
            raise FilmContextError("scene_ids must be a non-empty array")
        return get_keyframes(
            index_dir,
            [int(x) for x in ids],
            count_per_scene=int(arguments.get("count_per_scene", 2)),
            width=int(arguments.get("width", 768)),
            ffmpeg=_binary("ffmpeg", ffmpeg),
        )
    raise FilmContextError(f"Unknown Film Context tool: {tool}")


def _json_out(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 Edit Aja optional local Film Context index")
    p.add_argument("--ffmpeg", help="FFmpeg executable path")
    p.add_argument("--ffprobe", help="FFprobe executable path")
    sub = p.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("index", help="Build a local scene/dialogue index from a movie")
    cmd.add_argument("media", type=Path)
    cmd.add_argument("--srt", type=Path)
    cmd.add_argument("--index-dir", type=Path, required=True)
    cmd.add_argument("--scene-threshold", type=float, default=0.35)

    cmd = sub.add_parser("status", help="Show index status")
    cmd.add_argument("--index-dir", type=Path, required=True)

    cmd = sub.add_parser("search", help="Search local scenes")
    cmd.add_argument("query")
    cmd.add_argument("--index-dir", type=Path, required=True)
    cmd.add_argument("--top-k", type=int, default=5)
    cmd.add_argument("--near-scene", type=int)
    cmd.add_argument("--max-text-chars", type=int, default=420)

    cmd = sub.add_parser("scene", help="Read one scene")
    cmd.add_argument("scene_id", type=int)
    cmd.add_argument("--index-dir", type=Path, required=True)

    cmd = sub.add_parser("context", help="Read neighbor context around one scene")
    cmd.add_argument("scene_id", type=int)
    cmd.add_argument("--index-dir", type=Path, required=True)
    cmd.add_argument("--radius", type=int, default=2)

    cmd = sub.add_parser("annotate", help="Add/update local semantic notes for one scene")
    cmd.add_argument("scene_id", type=int)
    cmd.add_argument("notes")
    cmd.add_argument("--index-dir", type=Path, required=True)

    cmd = sub.add_parser("visual-index", help="Optionally build local OpenCLIP semantic visual tags once")
    cmd.add_argument("--index-dir", type=Path, required=True)
    cmd.add_argument("--model", default="ViT-B-32")
    cmd.add_argument("--pretrained", default="laion2b_s34b_b79k")
    cmd.add_argument("--device", default="auto")
    cmd.add_argument("--batch-size", type=int, default=8)
    cmd.add_argument("--tags-per-scene", type=int, default=8)
    cmd.add_argument("--width", type=int, default=512)
    cmd.add_argument("--force", action="store_true")

    cmd = sub.add_parser("keyframes", help="Generate a few candidate keyframes on demand")
    cmd.add_argument("scene_ids", nargs="+", type=int)
    cmd.add_argument("--index-dir", type=Path, required=True)
    cmd.add_argument("--count", type=int, default=2)
    cmd.add_argument("--width", type=int, default=768)

    sub.add_parser("tool-catalog", help="Print stable tools intended for AI/Gemini adapters")

    cmd = sub.add_parser("tool-call", help="Invoke one Film Context tool and print compact JSON")
    cmd.add_argument("tool")
    cmd.add_argument("--index-dir", type=Path, required=True)
    cmd.add_argument("--arguments", default="{}", help="JSON object")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "tool-catalog":
            _json_out(tool_catalog())
            return 0
        if args.command == "index":
            if not args.media.exists():
                raise FilmContextError(f"Media file not found: {args.media}")
            if args.srt and not args.srt.exists():
                raise FilmContextError(f"Subtitle file not found: {args.srt}")
            result = build_index(
                args.media,
                srt=args.srt,
                index_dir=args.index_dir,
                ffmpeg=_binary("ffmpeg", args.ffmpeg),
                ffprobe=_binary("ffprobe", args.ffprobe),
                threshold=args.scene_threshold,
            )
        elif args.command == "status":
            result = status(args.index_dir)
        elif args.command == "search":
            result = search_index(args.index_dir, args.query, top_k=args.top_k, near_scene=args.near_scene, max_text_chars=args.max_text_chars)
        elif args.command == "scene":
            result = get_scene(args.index_dir, args.scene_id)
        elif args.command == "context":
            result = get_context(args.index_dir, args.scene_id, radius=args.radius)
        elif args.command == "annotate":
            result = annotate_scene(args.index_dir, args.scene_id, args.notes)
        elif args.command == "visual-index":
            result = build_visual_semantic_tags(
                args.index_dir,
                ffmpeg=_binary("ffmpeg", args.ffmpeg),
                model_name=args.model,
                pretrained=args.pretrained,
                device=args.device,
                batch_size=args.batch_size,
                tags_per_scene=args.tags_per_scene,
                width=args.width,
                force=args.force,
            )
        elif args.command == "keyframes":
            result = get_keyframes(
                args.index_dir,
                args.scene_ids,
                count_per_scene=args.count,
                width=args.width,
                ffmpeg=_binary("ffmpeg", args.ffmpeg),
            )
        elif args.command == "tool-call":
            try:
                arguments = json.loads(args.arguments)
            except json.JSONDecodeError as exc:
                raise FilmContextError("--arguments must be valid JSON") from exc
            if not isinstance(arguments, dict):
                raise FilmContextError("--arguments must be a JSON object")
            result = invoke_tool(args.index_dir, args.tool, arguments, ffmpeg=args.ffmpeg)
        else:
            raise FilmContextError(f"Unsupported command: {args.command}")
        _json_out(result)
        return 0
    except (FilmContextError, OSError, ValueError, KeyError, sqlite3.Error) as exc:
        _json_out({"ok": False, "error": str(exc), "api_used": False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
