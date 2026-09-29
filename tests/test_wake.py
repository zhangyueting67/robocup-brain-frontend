import argparse
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from brain_frontend.__main__ import _run_wake_mode, parse_args
from brain_frontend.wake import extract_wake_command


class WakeTests(unittest.TestCase):
    def test_wake_mode_has_complete_launch_defaults(self):
        args = parse_args(["--wake"])
        self.assertEqual(args.planner, "llm")
        self.assertEqual(args.seconds, 8)
        self.assertEqual(args.wake_window, 3)
        self.assertEqual(args.wake_max_seconds, 15)
        self.assertEqual(args.pause_seconds, 1.5)
        self.assertEqual(args.command_pause_seconds, 0.8)
        self.assertTrue(args.speak)
        self.assertEqual(parse_args(["--wake", "--no-speak"]).speak, False)
        self.assertEqual(parse_args(["--text", "去客厅"]).planner, "rules")

    def test_wake_phrase_and_command_extraction(self):
        self.assertEqual(extract_wake_command("豆包豆包。"), "")
        self.assertEqual(extract_wake_command("你好，豆包豆包，去客厅找一个水瓶"), "去客厅找一个水瓶")
        self.assertEqual(extract_wake_command("豆包，豆包。去客厅"), "去客厅")
        self.assertIsNone(extract_wake_command("去客厅找一个水瓶"))
        self.assertIsNone(extract_wake_command("豆包，去客厅"))
        self.assertIsNone(extract_wake_command("请介绍豆包豆包的功能"))

    def test_wake_only_then_followup_command(self):
        args = argparse.Namespace(asr_provider=None, wake_window=3, wake_max_seconds=15,
                                  pause_seconds=1.2, command_pause_seconds=0.8,
                                  wake_min_rms=100, asr_model=None,
                                  seconds=8, speak=True, wake_once=True)
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / "wake.wav", Path(directory) / "command.wav"]
            for path in paths:
                path.touch()
            with patch("brain_frontend.speech.record_until_pause", side_effect=paths) as record, \
                 patch("brain_frontend.speech.wav_prefix", side_effect=lambda path, seconds: path), \
                 patch("brain_frontend.speech.transcribe_qwen", side_effect=["豆包豆包", "去客厅"]) as asr, \
                 patch("brain_frontend.speech.speak") as speak, \
                 patch("brain_frontend.__main__._process_command") as process:
                _run_wake_mode(args, lambda _: None)
            self.assertEqual(record.call_count, 2)
            self.assertEqual(record.call_args_list[0].kwargs["pause_seconds"], 1.2)
            self.assertEqual(record.call_args_list[1].kwargs["pause_seconds"], 0.8)
            self.assertEqual(asr.call_count, 2)
            speak.assert_called_once_with("我在，请说。")
            self.assertEqual(process.call_args.args[0], "去客厅")
            self.assertTrue(all(not path.exists() for path in paths))

    def test_ignores_non_wake_speech_and_accepts_inline_command(self):
        args = argparse.Namespace(asr_provider=None, wake_window=3, wake_max_seconds=15,
                                  pause_seconds=1.2, command_pause_seconds=0.8,
                                  wake_min_rms=100, asr_model=None,
                                  seconds=8, speak=False, wake_once=True)
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / "first.wav", Path(directory) / "second.wav"]
            for path in paths:
                path.touch()
            with patch("brain_frontend.speech.record_until_pause", side_effect=paths) as record, \
                 patch("brain_frontend.speech.wav_prefix", side_effect=lambda path, seconds: path), \
                 patch("brain_frontend.speech.transcribe_qwen", side_effect=["去厨房", "豆包，豆包，去客厅"]) as asr, \
                 patch("brain_frontend.__main__._process_command") as process:
                _run_wake_mode(args, lambda _: None)
            self.assertEqual(record.call_count, 2)
            self.assertEqual(asr.call_count, 2)
            process.assert_called_once()
            self.assertEqual(process.call_args.args[0], "去客厅")

    def test_long_utterance_checks_prefix_then_uses_complete_command(self):
        args = argparse.Namespace(asr_provider=None, wake_window=3, wake_max_seconds=15,
                                  pause_seconds=1.5, command_pause_seconds=0.8,
                                  wake_min_rms=100, asr_model=None, seconds=8,
                                  speak=False, wake_once=True)
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "long.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 16000 * 5)
            with patch("brain_frontend.speech.record_until_pause", return_value=audio), \
                 patch("brain_frontend.speech.transcribe_qwen",
                       side_effect=["豆包豆包，去客厅找", "去客厅找一个水瓶，找到后告诉我"]) as asr, \
                 patch("brain_frontend.__main__._process_command") as process:
                _run_wake_mode(args, lambda _: None)
            self.assertEqual(asr.call_count, 2)
            self.assertEqual(process.call_args.args[0], "去客厅找一个水瓶，找到后告诉我")
            self.assertFalse(audio.exists())


if __name__ == "__main__":
    unittest.main()
