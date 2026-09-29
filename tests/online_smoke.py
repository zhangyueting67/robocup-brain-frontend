"""Small paid/live integration check; run only with configured LLM_* variables."""

from __future__ import annotations

import time

from brain_frontend.planner import llm_plan


CASES = [
    ("去客厅。", ["navigate_to"]),
    ("去厨房。", ["navigate_to"]),
    ("去客厅找一个水瓶，找到之后告诉我。", ["navigate_to", "search_object", "report_result"]),
    ("返回起点。", ["return_home"]),
    ("去阳台找遥控器。", []),
]


def main() -> int:
    failed = 0
    for command, expected in CASES:
        started = time.monotonic()
        try:
            plan = llm_plan(command)
            actual = [step["skill"] for step in plan["steps"]]
            passed = actual == expected
            if command == "去厨房。" and passed:
                passed = plan["steps"][0]["args"] == {"location": "kitchen"}
            if command == "去客厅。" and passed:
                passed = plan["steps"][0]["args"] == {"location": "living_room"}
            print(f"{'PASS' if passed else 'FAIL'} {command} -> {actual} ({time.monotonic()-started:.1f}s)")
            if not passed:
                print(f"  实际计划: {plan}")
                failed += 1
        except Exception as exc:
            failed += 1
            print(f"ERROR {command} -> {type(exc).__name__}: {exc}")
    print(f"结果：{len(CASES) - failed}/{len(CASES)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
