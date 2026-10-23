"""Транскрипція записаних нарад через функцію в Modal (див. modal_app.py).

Приклади:
    python transcribe.py recordings\\meeting_2026-10-23_10-00-00.mp3
    python transcribe.py запис1.mp3 запис2.mp3 --srt

Поруч із кожним аудіофайлом з'являється .txt (і .srt з --srt).
У стерео-записі лівий канал — ви, правий — інші учасники.
Мова визначається для кожного фрагмента серед --languages (типово uk,en); рідкісні
мови з --extra-languages (типово lt,sv,lv,no,ru) обираються лише за впевненого визначення.
Якщо в нараді звучало кілька мов, біля реплік стоїть код мови; з --split-languages
поруч з'являються ще й окремі файли для кожної мови (зручно, коли є перекладач).
"""

import argparse
import os
import sys
import time

import soundfile as sf

APP_NAME = "teams-transcriber"
DEFAULT_LANGUAGES = "uk,en"
DEFAULT_EXTRA_LANGUAGES = "lt,sv,lv,no,ru"
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


def tag(seg, with_speakers, with_languages):
    parts = [seg["speaker"]] if with_speakers else []
    if with_languages:
        parts.append(f"({seg['language']})")
    return " ".join(parts)


def to_text(segments, with_speakers, with_languages=False):
    paragraphs = []
    for seg in segments:
        last = paragraphs[-1] if paragraphs else None
        if (last and last["speaker"] == seg["speaker"]
                and last["language"] == seg["language"]
                and seg["start"] - last["end"] <= MERGE_GAP_SECONDS):
            last["text"] += " " + seg["text"]
            last["end"] = seg["end"]
        else:
            paragraphs.append(dict(seg))
    lines = []
    for p in paragraphs:
        who = tag(p, with_speakers, with_languages)
        lines.append(f"[{format_time(p['start'])}] " + (f"{who}: " if who else "") + p["text"])
    return "\n\n".join(lines) + "\n"


def to_srt(segments, with_speakers, with_languages=False):
    blocks = []
    for i, seg in enumerate(segments, 1):
        who = tag(seg, with_speakers, with_languages)
        who = f"{who}: " if who else ""
        blocks.append(f"{i}\n{format_time(seg['start'], srt=True)} --> "
                      f"{format_time(seg['end'], srt=True)}\n{who}{seg['text']}\n")
    return "\n".join(blocks)


def get_transcriber():
    import modal

    return modal.Cls.from_name(APP_NAME, "Transcriber")()


def parse_codes(text):
    return [code.strip().lower() for code in text.split(",") if code.strip()]


def transcribe_file(path, transcriber, languages=parse_codes(DEFAULT_LANGUAGES),
                    extra_languages=parse_codes(DEFAULT_EXTRA_LANGUAGES),
                    labels=("Я", "Інші"), srt=False, split_languages=False):
    stereo = sf.info(path).channels == 2
    with open(path, "rb") as f:
        audio = f.read()

    print(f"Транскрипція: {path} ({len(audio) / 1024 / 1024:.1f} МБ, "
          f"{'стерео' if stereo else 'моно'}, мови: {', '.join(languages)}"
          + (f", рідкісні: {', '.join(extra_languages)}" if extra_languages else "")
          + ")...", flush=True)
    started = time.monotonic()
    from modal.exception import AuthError, NotFoundError

    try:
        channels = transcriber.transcribe.remote(
            audio, stereo, list(languages), list(extra_languages))
    except AuthError:
        sys.exit("Modal не авторизовано на цьому комп'ютері. Виконайте: modal token new")
    except NotFoundError:
        sys.exit(f"Застосунок «{APP_NAME}» не знайдено в Modal. "
                 "Розгорніть його: modal deploy modal_app.py")

    segments = label_segments(channels, labels if stereo else ("",))
    used = sorted({seg["language"] for seg in segments})
    multi = len(used) > 1
    base = os.path.splitext(path)[0]
    outputs = [f"{base}.txt"]
    with open(outputs[0], "w", encoding="utf-8") as f:
        f.write(to_text(segments, with_speakers=stereo, with_languages=multi))
    if split_languages and multi:
        for lang in used:
            outputs.append(f"{base}.{lang}.txt")
            with open(outputs[-1], "w", encoding="utf-8") as f:
                f.write(to_text([seg for seg in segments if seg["language"] == lang],
                                with_speakers=stereo))
    if srt:
        outputs.append(f"{base}.srt")
        with open(outputs[-1], "w", encoding="utf-8") as f:
            f.write(to_srt(segments, with_speakers=stereo, with_languages=multi))

    print(f"Готово за {time.monotonic() - started:.0f} с"
          + (f" (мови: {', '.join(used)})" if used else "") + f": {', '.join(outputs)}")
    return outputs


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Транскрипція записів нарад через Modal.")
    p.add_argument("files", nargs="+", help="аудіофайли (mp3, flac, wav)")
    p.add_argument("--languages", default=DEFAULT_LANGUAGES,
                   help="коди основних мов через кому; мова визначається для кожного "
                        f"фрагмента серед них (типово {DEFAULT_LANGUAGES})")
    p.add_argument("--extra-languages", default=DEFAULT_EXTRA_LANGUAGES,
                   help="рідкісні мови: обираються лише за впевненого визначення "
                        f"(типово {DEFAULT_EXTRA_LANGUAGES}); \"\" вимикає. Одна основна мова "
                        "без рідкісних вимикає визначення зовсім")
    p.add_argument("--labels", default="Я,Інші",
                   help="підписи лівого й правого каналу через кому (типово «Я,Інші»)")
    p.add_argument("--srt", action="store_true", help="також зберегти субтитри .srt")
    p.add_argument("--split-languages", action="store_true",
                   help="якщо звучало кілька мов, також зберегти окремий .txt для кожної "
                        "(напр. meeting.uk.txt, meeting.en.txt)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    labels = tuple(s.strip() for s in args.labels.split(",", 1))
    if len(labels) != 2:
        sys.exit("--labels: потрібні два підписи через кому, напр. «Я,Інші»")
    languages = parse_codes(args.languages)
    if not languages:
        sys.exit("--languages: вкажіть хоча б одну мову, напр. «uk»")
    extra_languages = [code for code in parse_codes(args.extra_languages)
                       if code not in languages]
    transcriber = get_transcriber()
    for path in args.files:
        transcribe_file(path, transcriber, languages, extra_languages, labels, args.srt,
                        args.split_languages)


if __name__ == "__main__":
    main()
