"""ROS2 bridge for the first two layers; use inside a sourced ROS2 environment."""

from __future__ import annotations

import argparse
import json
import queue
import threading
from typing import Any

from .feedback import feedback_text
from .planner import llm_plan, rule_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="人机交互与具身大脑 ROS2 桥接节点")
    parser.add_argument("--planner", choices=("rules", "llm"), default="rules")
    parser.add_argument("--mic", action="store_true", help="重复录音并送入规划器")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--asr-provider", choices=("whisper", "qwen"), default="whisper")
    parser.add_argument("--asr-model", default=None)
    parser.add_argument("--speak", action="store_true", help="播报执行结果")
    args = parser.parse_args()

    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class BrainNode(Node):
        def __init__(self) -> None:
            super().__init__("brain_frontend")
            self.plan_pub = self.create_publisher(String, "/brain/task_plan", 10)
            self.text_pub = self.create_publisher(String, "/brain/recognized_text", 10)
            self.create_subscription(String, "/brain/command_text", self.on_text, 10)
            self.create_subscription(String, "/brain/task_result", self.on_result, 10)
            self.inbox: queue.Queue[str] = queue.Queue()
            self.plans: dict[str, dict[str, Any]] = {}
            self.create_timer(0.1, self.drain_inbox)

        def on_text(self, msg: String) -> None:
            text = msg.data.strip()
            if text:
                self.inbox.put(text)

        def drain_inbox(self) -> None:
            while not self.inbox.empty():
                text = self.inbox.get_nowait()
                try:
                    plan = llm_plan(text) if args.planner == "llm" else rule_plan(text)
                    self.get_logger().info(f"识别文字: {text}")
                    text_msg = String()
                    text_msg.data = text
                    self.text_pub.publish(text_msg)
                    if plan["status"] != "ready":
                        self.get_logger().warning("指令不完整或不支持，需要用户澄清")
                        if args.speak:
                            from .speech import speak
                            speak("我没听明白任务，请再说一遍。")
                        continue
                    self.plans[plan["plan_id"]] = plan
                    msg = String()
                    msg.data = json.dumps(plan, ensure_ascii=False)
                    self.plan_pub.publish(msg)
                    self.get_logger().info(f"已发布任务计划: {plan['plan_id']}")
                except (ValueError, KeyError, OSError) as exc:
                    self.get_logger().error(f"规划失败: {exc}")

        def on_result(self, msg: String) -> None:
            try:
                result = json.loads(msg.data)
                plan = self.plans.get(result.get("plan_id"))
                if plan is None:
                    raise ValueError("未知 plan_id，忽略执行结果")
                message = feedback_text(result, plan)
                self.get_logger().info(message)
                if args.speak:
                    from .speech import speak
                    speak(message)
            except (ValueError, KeyError, ImportError) as exc:
                self.get_logger().error(f"执行反馈无效: {exc}")

    rclpy.init()
    node = BrainNode()

    if args.mic:
        def microphone_loop() -> None:
            from .speech import record_microphone, transcribe, transcribe_qwen

            while rclpy.ok():
                try:
                    path = record_microphone(args.seconds)
                    if args.asr_provider == "qwen":
                        text = transcribe_qwen(path, args.asr_model or "qwen3-asr-flash")
                    else:
                        text = transcribe(path, args.asr_model or "small")
                    path.unlink(missing_ok=True)
                    if text:
                        node.inbox.put(text)
                except Exception as exc:
                    node.get_logger().error(f"语音输入失败: {exc}")
                    break

        threading.Thread(target=microphone_loop, daemon=True).start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
