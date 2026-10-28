import csv
import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from export_dataset import export  # noqa: E402


def _wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def test_export_makes_audiofolder_and_filters_by_length(tmp_path):
    src = tmp_path / "rec"
    (src / "lmn" / "wavs").mkdir(parents=True)
    _wav(src / "lmn" / "wavs" / "a.wav", 2.0)
    _wav(src / "lmn" / "wavs" / "b.wav", 0.2)  # too short
    (src / "lmn" / "metadata.csv").write_text("a|तू कसो छ?|teertha\nb|हाँ|teertha\nc|missing|x\n", encoding="utf-8")
    out = tmp_path / "out"
    stats = export("lmn", src, out, 0.8, 20)
    assert stats == {"clips": 1, "skipped": 2, "minutes": 0.0, "speakers": 1}
    rows = list(csv.reader(io.StringIO((out / "metadata.csv").read_text(encoding="utf-8"))))
    assert rows == [["file_name", "text", "speaker"], ["data/a.wav", "तू कसो छ?", "teertha"]]
    assert (out / "data" / "a.wav").is_file()
