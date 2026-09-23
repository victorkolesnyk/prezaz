"""Запис звукової доріжки онлайн-зустрічі (Teams, Zoom, Meet) у файл.

Скрипт одночасно пише два джерела:
  * системний звук (loopback динаміків/навушників) — голоси інших учасників;
  * мікрофон — ваш голос.
Обидва потоки зводяться в один файл, придатний для транскрибування.

Приклади:
    python record_meeting.py                  # запис у ./recordings/*.mp3, зупинка Ctrl+C
    python record_meeting.py --list           # показати аудіопристрої
    python record_meeting.py --stereo         # ви в лівому каналі, співрозмовники в правому
    python record_meeting.py --format flac --duration 90
"""

import argparse
import contextlib
import datetime as dt
import os
import sys
import threading
import time

import numpy as np
import soundcard as sc
import soundfile as sf

# Скільки секунд звуку читати за один крок циклу
BLOCK_SECONDS = 0.1

FORMATS = {
    # Для MP3 compression_level=0.8 дає приблизно 40 кбіт/с (16 кГц моно),
    # тобто близько 18 МБ на годину: вкладається в ліміти більшості сервісів транскрибування.
    "mp3": {"format": "MP3", "subtype": "MPEG_LAYER_III",
            "compression_level": 0.8, "bitrate_mode": "CONSTANT"},
    "flac": {"format": "FLAC", "subtype": "PCM_16"},
    "wav": {"format": "WAV", "subtype": "PCM_16"},
}


def find_device(devices, name_part):
    matches = [d for d in devices if name_part.lower() in d.name.lower()]
    if not matches:
        names = "\n  ".join(d.name for d in devices)
        sys.exit(f"Пристрій, що містить «{name_part}», не знайдено. Доступні:\n  {names}")
    return matches[0]


def loopback_for(speaker):
    """Loopback-«мікрофон», що віддає звук, який грає на цих динаміках."""
    loopbacks = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    # Windows: той самий ідентифікатор кінцевої точки; PulseAudio/PipeWire: "<sink>.monitor"
    for m in loopbacks:
        if m.id in (speaker.id, f"{speaker.id}.monitor"):
            return m
    return sc.get_microphone(id=str(speaker.name), include_loopback=True)


def list_devices():
    print("Динаміки (звідси пишеться звук інших учасників):")
    default_spk = sc.default_speaker().name
    for spk in sc.all_speakers():
        mark = "  [типовий]" if spk.name == default_spk else ""
        print(f"  {spk.name}{mark}")
    print("\nМікрофони:")
    default_mic = sc.default_microphone().name
    for mic in sc.all_microphones():
        mark = "  [типовий]" if mic.name == default_mic else ""
        print(f"  {mic.name}{mark}")


def keep_loopback_alive(speaker, samplerate, stop_event):
    """Програє тишу в динаміки.

    WASAPI loopback у Windows не віддає даних, поки в системі нічого не звучить,
    і читання блокується. Тиша, що постійно грає, тримає потік безперервним,
    а доріжки мікрофона й динаміків синхронними.
    """
    silence = np.zeros((int(samplerate * BLOCK_SECONDS), 1), dtype="float32")
    with speaker.player(samplerate=samplerate, channels=1) as player:
        while not stop_event.is_set():
            player.play(silence)


def to_mono(block):
    return block.mean(axis=1) if block.ndim == 2 else block


def rms_db(block):
    rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
    return 20 * np.log10(rms) if rms > 1e-6 else -120.0


def level_bar(db, width=12):
    filled = int(max(0.0, min(1.0, (db + 60) / 60)) * width)
    return "#" * filled + "." * (width - filled)


def build_output_path(out_dir, name, fmt):
    os.makedirs(out_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = f"{name}_{stamp}" if name else f"meeting_{stamp}"
    return os.path.join(out_dir, f"{base}.{fmt}")


def record(args):
    speaker = (find_device(sc.all_speakers(), args.speaker)
               if args.speaker else sc.default_speaker())
    loopback = loopback_for(speaker)
    mic = None
    if not args.no_mic:
        mic = (find_device(sc.all_microphones(), args.mic)
               if args.mic else sc.default_microphone())

    channels = 2 if args.stereo else 1
    path = build_output_path(args.out, args.name, args.format)
    frames = int(args.samplerate * BLOCK_SECONDS)
    max_blocks = int(args.duration * 60 / BLOCK_SECONDS) if args.duration else None

    print(f"Динаміки:  {speaker.name}")
    print(f"Мікрофон:  {mic.name if mic else 'вимкнено'}")
    print(f"Файл:      {os.path.abspath(path)}")
    print("Запис почався. Зупинити: Ctrl+C."
          + (f" Автозупинка через {args.duration:g} хв." if args.duration else ""))
    print("Нагадування: попередьте учасників зустрічі, що ведеться запис.\n")

    stop_event = threading.Event()
    keeper = None
    if sys.platform == "win32":
        keeper = threading.Thread(target=keep_loopback_alive,
                                  args=(speaker, args.samplerate, stop_event),
                                  daemon=True)
        keeper.start()

    started = time.monotonic()
    last_status = 0.0
    blocks = 0
    with contextlib.ExitStack() as stack:
        out = stack.enter_context(sf.SoundFile(
            path, "w", samplerate=args.samplerate, channels=channels, **FORMATS[args.format]))
        spk_rec = stack.enter_context(loopback.recorder(samplerate=args.samplerate))
        mic_rec = (stack.enter_context(mic.recorder(samplerate=args.samplerate, channels=1))
                   if mic else None)
        stack.callback(stop_event.set)
        try:
            while max_blocks is None or blocks < max_blocks:
                others = to_mono(spk_rec.record(numframes=frames)) * args.speaker_gain
                if mic_rec is not None:
                    me = to_mono(mic_rec.record(numframes=frames)) * args.mic_gain
                else:
                    me = np.zeros_like(others)

                n = min(len(others), len(me))
                others, me = others[:n], me[:n]
                if args.stereo:
                    data = np.column_stack((me, others))
                else:
                    data = me + others
                out.write(np.clip(data, -1.0, 1.0).astype("float32"))
                blocks += 1

                now = time.monotonic()
                if now - last_status >= 1.0:
                    last_status = now
                    elapsed = int(now - started)
                    print(f"\r{elapsed // 3600:02d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}"
                          f"  співрозмовники [{level_bar(rms_db(others))}]"
                          f"  ви [{level_bar(rms_db(me))}]  ", end="", flush=True)
        except KeyboardInterrupt:
            pass

    if keeper:
        keeper.join(timeout=2)
    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"\n\nЗапис збережено: {os.path.abspath(path)} ({size_mb:.1f} МБ)")
    return path


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Запис звуку онлайн-зустрічі (системний звук + мікрофон) у файл.")
    p.add_argument("--list", action="store_true", help="показати аудіопристрої й вийти")
    p.add_argument("--out", default="recordings", help="тека для записів (типово ./recordings)")
    p.add_argument("--name", default="", help="префікс назви файлу, напр. назва зустрічі")
    p.add_argument("--format", choices=FORMATS, default="mp3", help="формат файлу (типово mp3)")
    p.add_argument("--samplerate", type=int, default=16000,
                   help="частота дискретизації, Гц (типово 16000, достатньо для мовлення)")
    p.add_argument("--stereo", action="store_true",
                   help="ви в лівому каналі, співрозмовники в правому")
    p.add_argument("--no-mic", action="store_true", help="не писати мікрофон")
    p.add_argument("--mic", help="частина назви мікрофона (типово системний)")
    p.add_argument("--speaker", help="частина назви динаміків/навушників (типово системні)")
    p.add_argument("--mic-gain", type=float, default=1.0, help="підсилення мікрофона")
    p.add_argument("--speaker-gain", type=float, default=1.0, help="підсилення системного звуку")
    p.add_argument("--duration", type=float, help="автозупинка через N хвилин")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.list:
        list_devices()
        return
    record(args)


if __name__ == "__main__":
    main()
