"""Offline demo planner and optional LLM planner."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .schema import LOCATIONS, OBJECTS, SKILLS, new_plan, validate_plan


def _provider_error_code(exc: urllib.error.HTTPError) -> str | None:
    """Classify a provider error without echoing its raw body or secrets."""
    try:
        body = exc.read(16384).decode("utf-8", errors="replace")
    except OSError:
        return None
    try:
        detail = json.loads(body)
    except ValueError:
        detail = None
    lowered = body.lower()
    if "incorrect api key" in lowered or "invalid api-key" in lowered or "invalid api key" in lowered:
        return "InvalidApiKey"
    if "not authorized to access this workspace" in lowered or "workspace does not exist" in lowered:
        return "WorkspaceNotAuthorized"
    if "invalid access token" in lowered or "token expired" in lowered:
        return "InvalidAccessToken"
    if isinstance(detail, dict):
        error = detail.get("error")
        candidates = [detail.get("code")]
        if isinstance(error, dict):
            candidates.extend((error.get("code"), error.get("type")))
        for candidate in candidates:
            if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_. -]{1,64}", candidate):
                return candidate
    return None


def _step(index: int, skill: str, args: dict[str, str], deps: list[str] | None = None) -> dict[str, Any]:
    return {"id": f"s{index}", "skill": skill, "args": args, "depends_on": deps or []}


def rule_plan(text: str) -> dict[str, Any]:
    """Limited, explicit baseline for integration before a model is available."""
    command = re.sub(r"[，。！？、\s]", "", text)
    if not command:
        raise ValueError("指令为空")
    if re.search(r"(停止|停下|取消任务|不要继续)", command):
        return new_plan(text, [_step(1, "stop", {})])
    if re.search(r"(返回起点|回到起点|返回原点|回家)", command):
        return new_plan(text, [_step(1, "return_home", {})])

    # The baseline must never execute only a known fragment of an unknown task.
    if re.search(r"(找|寻找|有没有|搜索)", command) and not re.search(r"(水瓶|瓶子)", command):
        return new_plan(text, [])
    if re.search(r"(去|前往|到(?=客厅|厨房))", command) and not re.search(r"(客厅|厨房)", command):
        return new_plan(text, [])

    location = next((code for word, code in (("客厅", "living_room"), ("厨房", "kitchen")) if word in command), None)
    object_name = "bottle" if "水瓶" in command or "瓶子" in command else None
    wants_search = bool(re.search(r"(找|寻找|有没有|搜索)", command))
    wants_report = bool(re.search(r"(告诉我|汇报|报告|说一声)", command))
    wants_move = bool(re.search(r"(去|前往|到(?=客厅|厨房))", command))

    steps: list[dict[str, Any]] = []
    if location and wants_move:
        steps.append(_step(len(steps) + 1, "navigate_to", {"location": location}))
    if object_name and wants_search:
        deps = [steps[-1]["id"]] if steps else []
        args = {"object": object_name}
        if location:
            args["location"] = location
        steps.append(_step(len(steps) + 1, "search_object", args, deps))
        if wants_report:
            steps.append(_step(len(steps) + 1, "report_result", {"source_step": steps[-1]["id"]}, [steps[-1]["id"]]))
    if not steps:
        return new_plan(text, [])
    return new_plan(text, steps)


def llm_plan(text: str) -> dict[str, Any]:
    """Call a configured Chat Completions endpoint; trust only validated output."""
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    model = os.environ.get("LLM_MODEL", "")
    if not base or not model:
        raise ValueError("LLM 模式需要 LLM_BASE_URL 和 LLM_MODEL")
    key = os.environ.get("LLM_API_KEY", "")
    system = (
        "你是家庭服务机器人的高层任务规划器。只输出 JSON 对象，不输出 Markdown。"
        "输出格式为 {\"steps\":[{\"id\":\"s1\",\"skill\":\"...\",\"args\":{},\"depends_on\":[]}]}。"
        f"只可使用技能 {sorted(SKILLS)}；地点 {sorted(LOCATIONS)}；物体 {sorted(OBJECTS)}。"
        "navigate_to 需要 location；search_object 需要 object，可含 location；"
        "report_result 需要 source_step，必须依赖之前的 search_object；return_home 与 stop 无参数。"
        "未知地点、未知物体、模糊或不支持的指令返回空 steps。"
        "不要推断搜索成功；report_result 的话术由实际执行结果决定。"
    )
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    thinking = os.environ.get("LLM_ENABLE_THINKING")
    if thinking is not None:
        if thinking.lower() not in {"true", "false"}:
            raise ValueError("LLM_ENABLE_THINKING 必须为 true 或 false")
        body["enable_thinking"] = thinking.lower() == "true"
    payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base + "/chat/completions", data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw_response = json.load(response)
    except urllib.error.HTTPError as exc:
        provider_code = _provider_error_code(exc)
        suffix = f"（服务端错误码：{provider_code}）" if provider_code else ""
        if exc.code == 401:
            raise ValueError(
                "模型服务返回 401" + suffix + "：请检查 API Key 是否正确，以及它与 Base URL 的地域、业务空间和套餐是否匹配"
            ) from exc
        raise ValueError(f"模型服务返回 HTTP {exc.code}{suffix}；请核对模型权限和请求参数") from exc
    content = raw_response["choices"][0]["message"]["content"]
    draft = json.loads(content)
    if not isinstance(draft, dict) or not isinstance(draft.get("steps"), list):
        raise ValueError("LLM 未返回合法 steps")
    return validate_plan(new_plan(text, draft["steps"]))
