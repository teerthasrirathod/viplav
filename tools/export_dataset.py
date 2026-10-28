"""Turn recordings from the Record page into a Hugging Face "audiofolder" dataset.

    python tools/export_dataset.py lmn            # -> dist/lmn-dataset/
    python tools/export_dataset.py lmn --min-seconds 1 --max-seconds 15

Load the result with `datasets.load_dataset("audiofolder", data_dir="dist/lmn-dataset")`.
Its columns are `audio`, `text` and `speaker`, which is what the MMS and Whisper fine-tuning
recipes expect (rename `text` if a recipe asks for `sentence` or `transcription`).
"""

import argparse
import csv
import shutil
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def export(lang: str, src: Path, out: Path, min_seconds: float, max_seconds: float) -> dict:
    meta = src / lang / "metadata.csv"
    if not meta.is_file():
        raise SystemExit(f"No recordings for {lang!r} in {src}")
    (out / "data").mkdir(parents=True, exist_ok=True)
    kept, skipped, seconds, speakers = 0, 0, 0.0, set()
    with (out / "metadata.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "text", "speaker"])
        for line in meta.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            clip_id, text, speaker = line.split("|")
            wav_path = src / lang / "wavs" / f"{clip_id}.wav"
            if not wav_path.is_file():
                skipped += 1
                continue
            with wave.open(str(wav_path)) as w:
                duration = w.getnframes() / w.getframerate()
            if not (min_seconds <= duration <= max_seconds):
                skipped += 1
                continue
            shutil.copy2(wav_path, out / "data" / wav_path.name)
            writer.writerow([f"data/{wav_path.name}", text, speaker])
            kept += 1
            seconds += duration
            speakers.add(speaker)
    return {"clips": kept, "skipped": skipped, "minutes": round(seconds / 60, 1), "speakers": len(speakers)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("lang", help="language code, e.g. lmn")
    parser.add_argument("--src", type=Path, default=ROOT / "data" / "recordings")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--min-seconds", type=float, default=0.8)
    parser.add_argument("--max-seconds", type=float, default=20.0)
    args = parser.parse_args()
    out = args.out or ROOT / "dist" / f"{args.lang}-dataset"
    stats = export(args.lang, args.src, out, args.min_seconds, args.max_seconds)
    print(f"{out}: {stats['clips']} clips, {stats['minutes']} min, {stats['speakers']} speaker(s); skipped {stats['skipped']}")


if __name__ == "__main__":
    main()
