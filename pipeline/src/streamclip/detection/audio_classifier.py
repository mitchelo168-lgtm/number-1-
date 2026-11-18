"""Audio-event highlight signal: laughter/cheering/crowd-reaction detection.

Runs a pretrained AudioSet audio-classification model (an Audio Spectrogram
Transformer by default) over rolling windows of decoded PCM from recorded
chunks, and reduces its label scores to a single highlight-relevant
confidence. The model itself is swappable and, for tests, fully replaceable
by injecting `classify` so the unit-test suite never has to load torch or
download model weights — only `tests -m slow` (see README) exercises the
real model, deliberately kept out of the default test run.
"""

import array
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"

# AudioSet label -> how strongly it implies a clip-worthy reaction moment.
TARGET_LABEL_WEIGHTS: dict[str, float] = {
    "Laughter": 1.0,
    "Belly laugh": 1.0,
    "Giggle": 0.8,
    "Chuckle, chortle": 0.8,
    "Cheering": 1.0,
    "Applause": 0.8,
    "Crowd": 0.6,
    "Shout": 0.7,
    "Yell": 0.7,
    "Screaming": 0.7,
    "Hubbub, speech noise, speech babble": 0.4,
}


@dataclass(frozen=True)
class AudioEventScore:
    offset_seconds: float
    top_label: str | None
    top_label_score: float
    event_confidence: float
    is_highlight: bool


ClassifyFn = Callable[[Sequence[float], int], list[dict]]


class AudioEventClassifier:
    def __init__(
        self,
        classify: ClassifyFn | None = None,
        confidence_threshold: float = 0.6,
        model_name: str = DEFAULT_MODEL_NAME,
        label_weights: dict[str, float] = TARGET_LABEL_WEIGHTS,
    ):
        self._classify = classify
        self._confidence_threshold = confidence_threshold
        self._model_name = model_name
        self._label_weights = label_weights
        self._pipeline = None

    def _ensure_classify_fn(self) -> ClassifyFn:
        if self._classify is not None:
            return self._classify
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "Audio event classification needs the optional 'audio' extras. "
                "Install with: pip install -e '.[audio]'"
            ) from exc

        if self._pipeline is None:
            self._pipeline = pipeline("audio-classification", model=self._model_name)

        def _run(samples: Sequence[float], sample_rate: int) -> list[dict]:
            result = self._pipeline({"array": list(samples), "sampling_rate": sample_rate}, top_k=10)
            return [{"label": r["label"], "score": r["score"]} for r in result]

        self._classify = _run
        return self._classify

    def score_window(self, samples: Sequence[float], sample_rate: int, offset_seconds: float) -> AudioEventScore:
        classify = self._ensure_classify_fn()
        results = classify(samples, sample_rate)

        top_label, top_score = None, 0.0
        event_confidence = 0.0
        for item in results:
            label, score = item["label"], item["score"]
            if score > top_score:
                top_label, top_score = label, score
            weight = self._label_weights.get(label, 0.0)
            event_confidence = max(event_confidence, weight * score)

        return AudioEventScore(
            offset_seconds=offset_seconds,
            top_label=top_label,
            top_label_score=top_score,
            event_confidence=event_confidence,
            is_highlight=event_confidence >= self._confidence_threshold,
        )


RunFfmpeg = Callable[[Path, float, float, int], Awaitable[bytes]]


async def _default_run_ffmpeg(chunk_path: Path, offset_seconds: float, duration_seconds: float, sample_rate: int) -> bytes:
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", str(offset_seconds), "-t", str(duration_seconds),
        "-i", str(chunk_path),
        "-f", "s16le", "-ac", "1", "-ar", str(sample_rate),
        "-",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await proc.communicate()
    return stdout


async def extract_audio_window(
    chunk_path: Path,
    offset_seconds: float,
    duration_seconds: float,
    sample_rate: int = 16000,
    run_ffmpeg: RunFfmpeg = _default_run_ffmpeg,
) -> tuple[list[float], int]:
    """Decode `duration_seconds` of mono PCM starting at `offset_seconds` into
    floats in [-1.0, 1.0], the shape HF audio-classification pipelines expect.
    """
    raw = await run_ffmpeg(chunk_path, offset_seconds, duration_seconds, sample_rate)
    ints = array.array("h")
    ints.frombytes(raw[: len(raw) - (len(raw) % 2)])
    samples = [s / 32768.0 for s in ints]
    return samples, sample_rate
