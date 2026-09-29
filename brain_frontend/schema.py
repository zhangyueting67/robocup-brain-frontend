"""Shared v1 contract. Validate model output before passing it to a robot."""

from __future__ import annotations

import uuid
from typing import Any

LOCATIONS = {"living_room", "kitchen"}
OBJECTS = {"bottle"}
SKILLS = {
    "navigate_to": {"required": {"location"}, "optional": set()},
    "search_object": {"required": {"object"}, "optional": {"location"}},
    "report_result": {"required": {"source_step"}, "optional": set()},
    "return_home": {"required": set(), "optional": set()},
    "stop": {"required": set(), "optional": set()},
}


def new_plan(source_text: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    plan = {
        "schema_version": "1.0",
        "plan_id": str(uuid.uuid4()),
        "source_text": source_text,
        "status": "ready" if steps else "needs_clarification",
        "steps": steps,
    }
    return validate_plan(plan)


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("schema_version") != "1.0":
        raise ValueError("plan 需要 schema_version=1.0")
    if not isinstance(plan.get("plan_id"), str) or not plan["plan_id"]:
        raise ValueError("plan_id 必须是非空字符串")
    if not isinstance(plan.get("source_text"), str) or not plan["source_text"].strip():
        raise ValueError("source_text 不能为空")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) > 10:
        raise ValueError("steps 必须是最多 10 项的数组")
    if plan.get("status") not in {"ready", "needs_clarification"}:
        raise ValueError("status 无效")
    if (plan["status"] == "ready") != bool(steps):
        raise ValueError("status 与 steps 不一致")

    known_ids: set[str] = set()
    step_by_id: dict[str, dict[str, Any]] = {}
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"id", "skill", "args", "depends_on"}:
            raise ValueError("每个 step 必须包含 id、skill、args、depends_on")
        step_id, skill, args, deps = (step[k] for k in ("id", "skill", "args", "depends_on"))
        if not isinstance(step_id, str) or not step_id or step_id in known_ids:
            raise ValueError("步骤 id 必须唯一且非空")
        if skill not in SKILLS:
            raise ValueError(f"技能不在白名单内: {skill}")
        if not isinstance(args, dict):
            raise ValueError("args 必须是对象")
        spec = SKILLS[skill]
        if not spec["required"] <= set(args) or not set(args) <= spec["required"] | spec["optional"]:
            raise ValueError(f"{skill} 参数不合法")
        if not isinstance(deps, list) or any(not isinstance(d, str) or d not in known_ids for d in deps):
            raise ValueError("depends_on 只能引用之前的步骤")
        if len(deps) != len(set(deps)):
            raise ValueError("depends_on 不能重复")
        if "location" in args and (not isinstance(args["location"], str) or args["location"] not in LOCATIONS):
            raise ValueError("未知地点")
        if "object" in args and (not isinstance(args["object"], str) or args["object"] not in OBJECTS):
            raise ValueError("未知物体")
        if skill == "report_result":
            source = args["source_step"]
            if not isinstance(source, str) or source not in step_by_id or step_by_id[source]["skill"] != "search_object":
                raise ValueError("report_result 必须引用之前的 search_object")
            if source not in deps:
                raise ValueError("report_result 必须依赖其搜索步骤")
        if skill == "stop" and len(steps) != 1:
            raise ValueError("stop 必须单独执行")
        known_ids.add(step_id)
        step_by_id[step_id] = step
    return plan
