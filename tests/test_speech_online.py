import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain_frontend.planner import rule_plan
from brain_frontend.speech import transcribe_qwen


class OnlineSpeechTests(unittest.TestCase):
    def test_audio_is_sent_and_transcript_feeds_planner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "command.wav"
            audio.write_bytes(b"RIFF-test-audio")

            def fake_open(request, timeout):
                self.assertEqual(request.full_url, "https://example.invalid/v1/chat/completions")
                self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
                self.assertEqual(timeout, 60)
                body = json.loads(request.data)
                self.assertEqual(body["model"], "qwen3-asr-flash")
                self.assertTrue(body["messages"][0]["content"][0]["input_audio"]["data"].startswith("data:audio/wav;base64,"))
                return io.BytesIO(json.dumps({"choices": [{"message": {"content": "去客厅找水瓶，找到后告诉我"}}]}).encode())

            with patch.dict(os.environ, {"LLM_BASE_URL": "https://example.invalid/v1", "LLM_API_KEY": "test-key", "ASR_BASE_URL": ""}):
                with patch("urllib.request.urlopen", side_effect=fake_open):
                    transcript = transcribe_qwen(audio)
            self.assertEqual([step["skill"] for step in rule_plan(transcript)["steps"]], ["navigate_to", "search_object", "report_result"])

    def test_missing_credentials_fail_before_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "LLM_API_KEY"):
                transcribe_qwen(Path("unused.wav"))



if __name__ == "__main__":
    unittest.main()
