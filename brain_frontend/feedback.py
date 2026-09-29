"""Turn actual execution results into grounded user feedback."""

from __future__ import annotations

from typing import Any


def feedback_text(result: dict[str, Any], plan: dict[str, Any] | None = None) -> str:
    if not isinstance(result, dict) or result.get("status") not in {"success", "failed", "cancelled"}:
        raise ValueError("执行结果需要有效 status")
    if not isinstance(result.get("plan_id"), str) or not isinstance(result.get("step_id"), str):
        raise ValueError("执行结果需要 plan_id 和 step_id")
    if plan is not None:
        if result["plan_id"] != plan["plan_id"]:
            raise ValueError("执行结果 plan_id 与当前计划不匹配")
        if result["step_id"] not in {step["id"] for step in plan["steps"]}:
            raise ValueError("执行结果 step_id 不属于当前计划")
    status = result["status"]
    if status == "cancelled":
        return "任务已取消。"
    if status == "failed":
        return "任务执行失败，请检查机器人状态。"
    data = result.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("data 必须是对象")
    if data.get("found") is True:
        return f"我已经找到{_object_label(data.get('object'))}。"
    if data.get("found") is False:
        return f"这次没有找到{_object_label(data.get('object'))}。"
    return "这一步已经完成。"


def _object_label(code: Any) -> str:
    return {"bottle": "水瓶"}.get(code, "目标物品")
