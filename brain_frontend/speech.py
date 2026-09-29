"""Optional speech dependencies are loaded only when needed."""

from __future__ import annotations

import base64
import math
import json
import os
import tempfile
import urllib.error
import urllib.request
import wave
from array import array
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Callable


def record_microphone(seconds: float = 5.0, sample_rate: int = 16000) -> Path:
    if seconds <= 0 or seconds > 30:
        raise ValueError("录音时长必须在 0 到 30 秒之间")
    import sounddevice as sd

    samples = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        path = Path(temp.name)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return path


def _pcm_rms(data: bytes) -> float:
    samples = array("h")
    samples.frombytes(data)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def record_until_pause(
    *,
    start_timeout: float = 3.0,
    max_seconds: float = 15.0,
    pause_seconds: float = 1.2,
    min_rms: float = 100.0,
    sample_rate: int = 16000,
    on_voice: Callable[[], None] | None = None,
) -> Path | None:
    """Record from first detected voice until a pause; return None if no voice starts."""
    if not 0 < start_timeout <= 30 or not 0 < max_seconds <= 30:
        raise ValueError("等待说话和最长录音时长必须在 0 到 30 秒之间")
    if not 0 < pause_seconds < max_seconds or min_rms <= 0:
        raise ValueError("停顿时长或音量阈值无效")
    import sounddevice as sd

    block_frames = sample_rate // 10  # 100 ms blocks
    block_seconds = block_frames / sample_rate
    start_blocks = math.ceil(start_timeout / block_seconds)
    max_blocks = math.ceil(max_seconds / block_seconds)
    pause_blocks = math.ceil(pause_seconds / block_seconds)
    preroll = deque(maxlen=3)
    frames: list[bytes] = []
    started = False
    silent_blocks = 0
    with sd.RawInputStream(samplerate=sample_rate, channels=1, dtype="int16", blocksize=block_frames) as stream:
        for index in range(max_blocks):
            data, _overflowed = stream.read(block_frames)
            block = bytes(data)
            voiced = _pcm_rms(block) >= min_rms
            if not started:
                if voiced:
                    started = True
                    frames.extend(preroll)
                    frames.append(block)
                    if on_voice:
                        on_voice()
                else:
                    preroll.append(block)
                    if index + 1 >= start_blocks:
                        return None
                continue
            frames.append(block)
            silent_blocks = 0 if voiced else silent_blocks + 1
            if silent_blocks >= pause_blocks:
                break
    if not started:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        path = Path(temp.name)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return path


def wav_rms(audio_path: Path) -> float:
    """RMS amplitude of a mono 16-bit WAV, used to skip obvious silence."""
    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("唤醒监听需要单声道 16 位 WAV")
        return _pcm_rms(wav.readframes(wav.getnframes()))


def wav_prefix(audio_path: Path, seconds: float = 3.0) -> Path:
    """Return a short WAV prefix, or the original path if already short enough."""
    with wave.open(str(audio_path), "rb") as source:
        frame_limit = int(seconds * source.getframerate())
        if source.getnframes() <= frame_limit:
            return audio_path
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(frame_limit)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        prefix_path = Path(temp.name)
    with wave.open(str(prefix_path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(frames)
    return prefix_path


@lru_cache(maxsize=2)
def _asr_model(model_name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="auto", compute_type="default")


def transcribe(
    audio_path: Path,
    model_name: str = "small",
    progress: Callable[[str], None] | None = None,
) -> str:
    if progress:
        progress(f"正在加载语音模型 {model_name}（首次使用可能需要下载）…")
    model = _asr_model(model_name)
    if progress:
        progress("语音模型已就绪，正在识别…")
    segments, _ = model.transcribe(str(audio_path), language="zh", vad_filter=True)
    return "".join(segment.text for segment in segments).strip()


def transcribe_qwen(audio_path: Path, model_name: str = "qwen3-asr-flash") -> str:
    """Recognize a short audio file via the configured Model Studio endpoint."""
    base = os.environ.get("ASR_BASE_URL") or os.environ.get("LLM_BASE_URL", "")
    key = os.environ.get("LLM_API_KEY", "")
    if not base or not key:
        raise ValueError("在线 ASR 需要 LLM_BASE_URL（或 ASR_BASE_URL）和 LLM_API_KEY")
    mime_types = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac"}
    mime = mime_types.get(audio_path.suffix.lower())
    if mime is None:
        raise ValueError("在线 ASR 当前支持 WAV、MP3、FLAC 文件")
    audio_bytes = audio_path.read_bytes()
    if not audio_bytes or len(audio_bytes) > 7_000_000:
        raise ValueError("音频为空或过大；在线 ASR 的 Base64 请求限制为 10 MB")
    data_uri = f"data:{mime};base64,{base64.b64encode(audio_bytes).decode('ascii')}"
    body = {
        "model": model_name,
        "messages": [{
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
        }],
        "stream": False,
        "asr_options": {"language": "zh"},
    }
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        from .planner import _provider_error_code

        code = _provider_error_code(exc)
        suffix = f"（服务端错误码：{code}）" if code else ""
        raise ValueError(f"在线 ASR 返回 HTTP {exc.code}{suffix}；请检查模型权限、地域和 API Key") from exc
    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("在线 ASR 返回格式不符合预期") from exc
    if not isinstance(text, str):
        raise ValueError("在线 ASR 未返回文字")
    return text.strip()


def speak(text: str) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
