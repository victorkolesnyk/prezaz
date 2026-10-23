"""Транскрипція записів нарад на хмарній відеокарті Modal (faster-whisper large-v3).

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


def transcribe_channels(pipeline, audio_bytes, stereo, language, batch_size=16):
    """Повертає список каналів; кожен канал — список сегментів {start, end, text}.

    Винесено окремо від Modal, щоб логіку можна було перевірити локально.
    """
    from faster_whisper.audio import decode_audio

    decoded = decode_audio(io.BytesIO(audio_bytes), split_stereo=stereo)
    channels = list(decoded) if stereo else [decoded]

    result = []
    for samples in channels:
        segments, _info = pipeline.transcribe(
            samples, language=language, batch_size=batch_size, vad_filter=True)
        result.append([
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments if s.text.strip()
        ])
    return result


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
        self.pipeline = BatchedInferencePipeline(model=model)

    @modal.method()
    def transcribe(self, audio_bytes: bytes, stereo: bool, language: str = "uk"):
        return transcribe_channels(self.pipeline, audio_bytes, stereo, language)
