"""Транскрипція записів нарад на хмарній відеокарті Modal (faster-whisper large-v3).

Мова визначається для кожного фрагмента мовлення серед основних мов (uk, en), а рідкісні
(lt, sv, lv, no, ru) обираються лише за впевненого визначення.

Розгортання (один раз і після кожної зміни цього файлу):
    modal deploy modal_app.py

Після цього transcribe.py і record_meeting.py --transcribe викликають функцію
за назвою застосунку. Відеокарта вмикається лише на час обробки, оплата посекундна.

Код функції не пише аудіо й текст на диск і не логує їх; модель зберігається в томі
Modal, щоб не завантажувати її при кожному запуску. Сам Modal тримає вхідні й вихідні
дані функцій (аудіо й текст) зашифрованими до 7 днів, потім видаляє (див. його Security guide).
"""

import io

import modal

APP_NAME = "teams-transcriber"
MODEL_NAME = "large-v3"
MODEL_DIR = "/models"

app = modal.App(APP_NAME)

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
    .pip_install("faster-whisper==1.2.1")
)
models_volume = modal.Volume.from_name("teams-transcriber-models", create_if_missing=True)


# Фрагменти мовлення, коротші за це, успадковують мову сусіднього фрагмента:
# на кількох словах визначення мови ненадійне.
MIN_DETECT_SECONDS = 2.0
WINDOW_SECONDS = 30.0  # більше Whisper за один прохід не обробляє
# Рідкісна мова призначається фрагменту лише за такої ймовірності: інакше англійське
# чи українське мовлення з акцентом могло б «перейти» в близьку рідкісну мову.
EXTRA_MIN_PROB = 0.6
# Для мов, близьких до основних, поріг вищий. Whisper часто дає українському мовленню
# помітну ймовірність російської, тож російська обирається лише за майже певного визначення.
EXTRA_MIN_PROB_BY_LANGUAGE = {"ru": 0.85}


def speech_segments(samples, sampling_rate=16000):
    """Фрагменти мовлення між паузами (за VAD), кожен до 30 с; [(start_s, end_s)]."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    # Запас 0,2 с замість типових 0,4 с, щоб пауза між оригіналом і перекладом
    # не «злипалася» і межа зміни мови лишалася видимою.
    speech = get_speech_timestamps(samples, VadOptions(
        max_speech_duration_s=WINDOW_SECONDS, min_silence_duration_ms=160, speech_pad_ms=200))
    return [(seg["start"] / sampling_rate, seg["end"] / sampling_rate) for seg in speech]


def group_windows(segments, langs):
    """Зливає сусідні фрагменти однієї мови у вікна до 30 с: [((start, end), lang)]."""
    windows = []
    for (start, end), lang in zip(segments, langs):
        if windows and windows[-1][1] == lang and end - windows[-1][0][0] <= WINDOW_SECONDS:
            windows[-1] = ((windows[-1][0][0], end), lang)
        else:
            windows.append(((start, end), lang))
    return windows


def pick_language(model, chunk, languages, extra_languages=()):
    """Мова фрагмента: найімовірніша з основних, або рідкісна, якщо вона впевнено вища."""
    _lang, _prob, all_probs = model.detect_language(audio=chunk)
    probs = dict(all_probs)
    main = max(languages, key=lambda lang: probs.get(lang, 0.0))
    if extra_languages:
        extra = max(extra_languages, key=lambda lang: probs.get(lang, 0.0))
        threshold = EXTRA_MIN_PROB_BY_LANGUAGE.get(extra, EXTRA_MIN_PROB)
        if probs.get(extra, 0.0) >= threshold and probs[extra] > probs.get(main, 0.0):
            return extra
    return main


def detect_segment_languages(model, samples, segments, languages, extra_languages,
                             sampling_rate=16000):
    """Мова кожного фрагмента окремо: при послідовному перекладі мова змінюється
    кожні кілька речень. Короткі фрагменти успадковують мову ближчого за часом сусіда."""
    langs = []
    for start, end in segments:
        if end - start < MIN_DETECT_SECONDS:
            langs.append(None)
        else:
            chunk = samples[int(start * sampling_rate):int(end * sampling_rate)]
            langs.append(pick_language(model, chunk, languages, extra_languages))
    if all(lang is None for lang in langs):
        return [languages[0]] * len(segments)

    resolved = list(langs)
    for i, lang in enumerate(langs):
        if lang is not None:
            continue
        left = i - 1 if i > 0 else None
        right = next((j for j in range(i + 1, len(langs)) if langs[j] is not None), None)
        # Напрямок обираємо за паузою до безпосереднього сусіда: фрагменти, між якими
        # паузи майже немає, найімовірніше належать одній репліці.
        gap_left = segments[i][0] - segments[i - 1][1] if i > 0 else float("inf")
        gap_right = (segments[i + 1][0] - segments[i][1]
                     if i + 1 < len(segments) else float("inf"))
        if left is None or (right is not None and gap_right < gap_left):
            resolved[i] = langs[right]
        else:
            # Лівий сусід уже розв'язаний, тож мова передається ланцюжком
            resolved[i] = resolved[i - 1]
    return resolved


def transcribe_channel(model, pipeline, samples, languages, extra_languages, batch_size,
                       sampling_rate=16000):
    segments = speech_segments(samples, sampling_rate)
    if not segments:
        return []

    if len(languages) == 1 and not extra_languages:
        langs = [languages[0]] * len(segments)
    else:
        langs = detect_segment_languages(model, samples, segments, languages, extra_languages,
                                         sampling_rate)
    windows = group_windows(segments, langs)

    result = []
    for lang in sorted(set(langs)):
        clips = [{"start": start, "end": end} for (start, end), wl in windows if wl == lang]
        found, _info = pipeline.transcribe(
            samples, language=lang, clip_timestamps=clips, batch_size=batch_size)
        result.extend(
            {"start": round(s.start, 2), "end": round(s.end, 2),
             "text": s.text.strip(), "language": lang}
            for s in found if s.text.strip())
    return sorted(result, key=lambda seg: seg["start"])


def transcribe_channels(model, pipeline, audio_bytes, stereo, languages, extra_languages=(),
                        batch_size=16):
    """Повертає список каналів; кожен канал — сегменти {start, end, text, language}.

    Мова визначається для кожного фрагмента мовлення окремо, лише серед `languages` та
    `extra_languages` (останні — за ймовірності від EXTRA_MIN_PROB): так нарада може
    переходити з української на англійську, а українська не сплутується з близькими
    мовами поза списком.
    Винесено окремо від Modal, щоб логіку можна було перевірити локально.
    """
    from faster_whisper.audio import decode_audio

    decoded = decode_audio(io.BytesIO(audio_bytes), split_stereo=stereo)
    channels = list(decoded) if stereo else [decoded]
    return [transcribe_channel(model, pipeline, samples, languages, extra_languages, batch_size)
            for samples in channels]


@app.cls(gpu="L4", image=image, volumes={MODEL_DIR: models_volume},
         timeout=60 * 60, scaledown_window=30, max_containers=1)
class Transcriber:
    @modal.enter()
    def load(self):
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16",
                             download_root=MODEL_DIR)
        # При першому запуску модель щойно завантажилась: зберігаємо її в томі
        models_volume.commit()
        self.model = model
        self.pipeline = BatchedInferencePipeline(model=model)

    @modal.method()
    def transcribe(self, audio_bytes: bytes, stereo: bool, languages: list,
                   extra_languages: list = ()):
        return transcribe_channels(self.model, self.pipeline, audio_bytes, stereo,
                                   languages, extra_languages)
