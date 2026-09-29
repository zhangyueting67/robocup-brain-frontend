import unittest
import io
import urllib.error

from brain_frontend.planner import _provider_error_code

from brain_frontend.feedback import feedback_text
from brain_frontend.planner import rule_plan
from brain_frontend.schema import new_plan


class BrainTests(unittest.TestCase):
    def test_demo_plan(self):
        steps = rule_plan("去客厅找一个水瓶，找到之后告诉我")["steps"]
        self.assertEqual([step["skill"] for step in steps], ["navigate_to", "search_object", "report_result"])
        self.assertEqual(steps[2]["args"]["source_step"], "s2")

    def test_other_demo_commands(self):
        cases = {
            "去客厅": ["navigate_to"],
            "去厨房": ["navigate_to"],
            "找到水瓶之后告诉我": ["search_object", "report_result"],
            "返回起点": ["return_home"],
            "停止任务": ["stop"],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual([s["skill"] for s in rule_plan(text)["steps"]], expected)

    def test_unknown_command_requests_clarification(self):
        self.assertEqual(rule_plan("去阳台找遥控器")["status"], "needs_clarification")
        self.assertEqual(rule_plan("去客厅找遥控器")["status"], "needs_clarification")

    def test_reject_unapproved_skill(self):
        with self.assertRaises(ValueError):
            new_plan("向前冲", [{"id": "s1", "skill": "cmd_vel", "args": {}, "depends_on": []}])

    def test_report_must_depend_on_search(self):
        with self.assertRaises(ValueError):
            new_plan("找到后告诉我", [
                {"id": "s1", "skill": "search_object", "args": {"object": "bottle"}, "depends_on": []},
                {"id": "s2", "skill": "report_result", "args": {"source_step": "s1"}, "depends_on": []},
            ])

    def test_feedback_depends_on_real_detection(self):
        result = {"plan_id": "p", "step_id": "s2", "status": "success", "data": {"found": False}}
        self.assertIn("没有找到", feedback_text(result))
        result["data"]["found"] = True
        self.assertIn("已经找到", feedback_text(result))

    def test_feedback_rejects_wrong_plan(self):
        plan = rule_plan("去客厅")
        with self.assertRaises(ValueError):
            feedback_text({"plan_id": "wrong", "step_id": "s1", "status": "success"}, plan)

    def test_provider_error_code_does_not_expose_message(self):
        body = io.BytesIO(b'{"code":"InvalidApiKey","message":"secret-value"}')
        error = urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, body)
        self.assertEqual(_provider_error_code(error), "InvalidApiKey")

    def test_provider_error_code_classifies_plain_message(self):
        body = io.BytesIO(b'{"message":"Incorrect API key provided: secret-value"}')
        error = urllib.error.HTTPError("https://example.invalid", 401, "Unauthorized", {}, body)
        self.assertEqual(_provider_error_code(error), "InvalidApiKey")


if __name__ == "__main__":
    unittest.main()
