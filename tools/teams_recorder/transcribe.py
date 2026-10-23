"""Транскрипція записаних нарад через функцію в Modal (див. modal_app.py).

Приклади:
    python transcribe.py recordings\\meeting_2026-10-23_10-00-00.mp3
    python transcribe.py запис1.mp3 запис2.mp3 --srt

Поруч із кожним аудіофайлом з'являється .txt (і .srt з --srt).
У стерео-записі лівий канал — ви, правий — інші учасники.
"""

import argparse
import os
import sys
import time

import soundfile as sf

APP_NAME = "teams-transcriber"
# Якщо дві репліки однієї сторони розділяє менша пауза, вони зливаються в один абзац
MERGE_GAP_SECONDS = 3.0


def format_time(seconds, srt=False):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}" if srt else f"{h:02d}:{m:02d}:{s:02d}"


def label_segments(channels, labels):
    """Зводить сегменти всіх каналів в один список, відсортований за часом."""
    merged = []
    for label, segments in zip(labels, channels):
        merged.extend({**seg, "speaker": label} for seg in segments)
    return sorted(merged, key=lambda seg: seg["start"])


def to_text(segments, with_speakers):
    paragraphs = []
    for seg in segments:
        last = paragraphs[-1] if paragraphs else None
        if (last and last["speaker"] == seg["speaker"]
                and seg["start"] - last["end"] <= MERGE_GAP_SECONDS):
            last["text"] += " " + seg["text"]
            last["end"] = seg["end"]
        else:
            paragraphs.append(dict(seg))
    lines = []
    for p in paragraphs:
        who = f" {p['speaker']}:" if with_speakers else ""
        lines.append(f"[{format_time(p['start'])}]{who} {p['text']}")
    return "\n\n".join(lines) + "\n"


def to_srt(segments, with_speakers):
    blocks = []
    for i, seg in enumerate(segments, 1):
        who = f"{seg['speaker']}: " if with_speakers else ""
        blocks.append(f"{i}\n{format_time(seg['start'], srt=True)} --> "
                      f"{format_time(seg['end'], srt=True)}\n{who}{seg['text']}\n")
    return "\n".join(blocks)


def get_transcriber():
    import modal

    return modal.Cls.from_name(APP_NAME, "Transcriber")()


def transcribe_file(path, transcriber, language="uk", labels=("Я", "Інші"), srt=False):
    stereo = sf.info(path).channels == 2
    with open(path, "rb") as f:
        audio = f.read()

    print(f"Транскрипція: {path} ({len(audio) / 1024 / 1024:.1f} МБ, "
          f"{'стерео' if stereo else 'моно'})...", flush=True)
    started = time.monotonic()
    from modal.exception import AuthError, NotFoundError

    try:
        channels = transcriber.transcribe.remote(audio, stereo, language)
    except AuthError:
        sys.exit("Modal не авторизовано на цьому комп'ютері. Виконайте: modal token new")
    except NotFoundError:
        sys.exit(f"Застосунок «{APP_NAME}» не знайдено в Modal. "
                 "Розгорніть його: modal deploy modal_app.py")

    segments = label_segments(channels, labels if stereo else ("",))
    base = os.path.splitext(path)[0]
    outputs = [f"{base}.txt"]
    with open(outputs[0], "w", encoding="utf-8") as f:
        f.write(to_text(segments, with_speakers=stereo))
    if srt:
        outputs.append(f"{base}.srt")
        with open(outputs[1], "w", encoding="utf-8") as f:
            f.write(to_srt(segments, with_speakers=stereo))

    print(f"Готово за {time.monotonic() - started:.0f} с: {', '.join(outputs)}")
    return outputs


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Транскрипція записів нарад через Modal.")
    p.add_argument("files", nargs="+", help="аудіофайли (mp3, flac, wav)")
    p.add_argument("--language", default="uk", help="мова мовлення (типово uk)")
    p.add_argument("--labels", default="Я,Інші",
                   help="підписи лівого й правого каналу через кому (типово «Я,Інші»)")
    p.add_argument("--srt", action="store_true", help="також зберегти субтитри .srt")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    labels = tuple(s.strip() for s in args.labels.split(",", 1))
    if len(labels) != 2:
        sys.exit("--labels: потрібні два підписи через кому, напр. «Я,Інші»")
    transcriber = get_transcriber()
    for path in args.files:
        transcribe_file(path, transcriber, args.language, labels, args.srt)


if __name__ == "__main__":
    main()
