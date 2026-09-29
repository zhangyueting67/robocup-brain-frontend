import sys
import types
import unittest
import wave
from array import array
from unittest.mock import patch

from brain_frontend.speech import record_until_pause


def _block(amplitude: int) -> bytes:
    return array("h", [amplitude] * 1600).tobytes()


class FakeStream:
    def __init__(self, blocks):
        self.blocks = iter(blocks)
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, frames):
        assert frames == 1600
        self.read_count += 1
        return next(self.blocks), False


class PauseRecordingTests(unittest.TestCase):
    def test_records_complete_utterance_then_stops_after_pause(self):
        # Voice extends beyond the old 3-second cutoff; two short gaps are not the end.
        blocks = ([_block(0)] * 2 + [_block(1000)] * 15 + [_block(0)] * 4
                  + [_block(1000)] * 17 + [_block(0)] * 12 + [_block(1000)] * 10)
        stream = FakeStream(blocks)
        callbacks = []
        with patch.dict(sys.modules, {"sounddevice": types.SimpleNamespace(RawInputStream=lambda **_: stream)}):
            path = record_until_pause(start_timeout=3, max_seconds=10,
                                      pause_seconds=1.2, min_rms=100,
                                      on_voice=lambda: callbacks.append(True))
        try:
            with wave.open(str(path), "rb") as audio:
                self.assertGreater(audio.getnframes() / audio.getframerate(), 3)
                self.assertEqual(audio.getnframes() / audio.getframerate(), 5.0)
            self.assertEqual(stream.read_count, 50)
            self.assertEqual(callbacks, [True])
        finally:
            path.unlink()

    def test_returns_none_if_nobody_speaks(self):
        stream = FakeStream([_block(0)] * 3)
        with patch.dict(sys.modules, {"sounddevice": types.SimpleNamespace(RawInputStream=lambda **_: stream)}):
            self.assertIsNone(record_until_pause(start_timeout=0.3, max_seconds=3,
                                                 pause_seconds=1.2, min_rms=100))
        self.assertEqual(stream.read_count, 3)
