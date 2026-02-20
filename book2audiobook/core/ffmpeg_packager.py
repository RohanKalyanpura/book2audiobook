from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def find_binary(name: str) -> str | None:
    import sys
    from pathlib import Path
    
    # 1. Check sys._MEIPASS (PyInstaller one-file bundled mode)
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(getattr(sys, "_MEIPASS"))
            candidate = meipass / name
            if candidate.exists():
                return str(candidate)
            win_candidate = meipass / f"{name}.exe"
            if win_candidate.exists():
                return str(win_candidate)
                
        # 2. Check executable parent dir (PyInstaller folder mode)
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / name
        if candidate.exists():
            return str(candidate)
        win_candidate = exe_dir / f"{name}.exe"
        if win_candidate.exists():
            return str(win_candidate)
            
    # 3. Fallback to system PATH
    return shutil.which(name)

def verify_ffmpeg() -> tuple[str | None, str | None]:
    return find_binary("ffmpeg"), find_binary("ffprobe")


def ffprobe_duration(ffprobe_bin: str, path: Path) -> float:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    return float(data["format"]["duration"])


def loudnorm_chapter(ffmpeg_bin: str, source: Path, target: Path) -> None:
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(source),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
        str(target),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def build_ffmetadata(chapters: list[tuple[str, float]], out_path: Path) -> None:
    lines = [";FFMETADATA1"]
    cursor_ms = 0
    for title, duration_seconds in chapters:
        start = cursor_ms
        end = cursor_ms + int(duration_seconds * 1000)
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start}",
                f"END={end}",
                f"title={title}",
            ]
        )
        cursor_ms = end
    out_path.write_text("\n".join(lines), encoding="utf-8")


def package_m4b(
    ffmpeg_bin: str,
    chapter_audio_file: Path,
    ffmetadata_file: Path,
    output_file: Path,
    bitrate_kbps: int,
    title: str,
    author: str,
    cover_file: Path | None,
) -> None:
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(chapter_audio_file),
        "-i",
        str(ffmetadata_file),
    ]
    if cover_file and cover_file.exists():
        cmd.extend(["-i", str(cover_file)])

    cmd.extend(
        [
            "-map",
            "0:a",
            "-map_metadata",
            "1",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-b:a",
            f"{bitrate_kbps}k",
            "-metadata",
            f"title={title}",
            "-metadata",
            f"artist={author}",
        ]
    )

    if cover_file and cover_file.exists():
        cmd.extend(["-map", "2", "-c:v", "copy", "-disposition:v", "attached_pic"])

    cmd.append(str(output_file))
    subprocess.run(cmd, check=True, capture_output=True)
