"""CLI for text, audio file and microphone demos."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .feedback import feedback_text
from .planner import llm_plan, rule_plan

WAKE_DEFAULTS = {
    "planner": "llm",
    "seconds": 8.0,
    "speak": True,
    "wake_window": 3.0,
    "wake_max_seconds": 15.0,
    "pause_seconds": 1.5,
    "command_pause_seconds": 0.8,
    "wake_min_rms": 100.0,
}


def _process_command(text: str, args: argparse.Namespace, progress) -> None:
    if not text.strip():
        raise ValueError("未识别到语音文字，请重试")
    print(json.dumps({"utterance": {"schema_version": "1.0", "text": text}}, ensure_ascii=False, indent=2))
    if args.planner == "llm":
        progress("文字识别完成，正在请求在线规划模型…")
    plan = llm_plan(text) if args.planner == "llm" else rule_plan(text)
    print(json.dumps({"plan": plan}, ensure_ascii=False, indent=2))
    if args.speak:
        from .speech import speak

        message = "任务计划已生成。" if plan["status"] == "ready" else "我没听明白任务，请再说一遍。"
        progress("正在语音播报确认…")
        speak(message)
        progress("语音播报调用完成。")


def _run_wake_mode(args: argparse.Namespace, progress) -> None:
    from .speech import record_until_pause, speak, transcribe_qwen, wav_prefix
    from .wake import WAKE_PHRASE, extract_wake_command

    if args.asr_provider not in (None, "qwen"):
        raise ValueError("唤醒模式目前使用在线 Qwen ASR；请移除 --asr-provider whisper")
    if not 0 < args.wake_window <= 30:
        raise ValueError("--wake-window 必须在 0 到 30 秒之间")
    if not 0 < args.wake_max_seconds <= 30 or not 0 < args.seconds <= 30:
        raise ValueError("最长录音时长必须在 0 到 30 秒之间")
    if not 0 < args.pause_seconds < args.wake_max_seconds:
        raise ValueError("--pause-seconds 必须大于 0，且小于 --wake-max-seconds")
    if not 0 < args.command_pause_seconds < args.seconds:
        raise ValueError("--command-pause-seconds 必须大于 0，且小于 --seconds")
    if args.wake_min_rms <= 0:
        raise ValueError("--wake-min-rms 必须大于 0")
    model = args.asr_model or "qwen3-asr-flash"
    progress(f"正在监听唤醒词“{WAKE_PHRASE}”（按 Ctrl+C 结束）…")
    while True:
        audio = record_until_pause(
            start_timeout=args.wake_window,
            max_seconds=args.wake_max_seconds,
            pause_seconds=args.pause_seconds,
            min_rms=args.wake_min_rms,
            on_voice=lambda: progress("检测到说话，等待明显停顿…"),
        )
        if audio is None:
            continue
        prefix = audio
        try:
            prefix = wav_prefix(audio, seconds=3.0)
            progress("录音结束，正在识别开头的唤醒词…")
            recognized = transcribe_qwen(prefix, model)
            progress(f"唤醒监听识别结果：{recognized or '（空）'}")
            command = extract_wake_command(recognized)
            if command is None:
                progress("未识别到唤醒词，继续监听…")
                continue
            if prefix != audio:
                progress("已识别唤醒词，正在识别完整指令…")
                full_text = transcribe_qwen(audio, model)
                progress(f"完整录音识别结果：{full_text or '（空）'}")
                full_command = extract_wake_command(full_text)
                command = full_command if full_command is not None else full_text
                if command.strip(" ，。.!！?？") in ("嗯", "啊", "呃", "哦"):
                    command = ""
        finally:
            if prefix != audio:
                prefix.unlink(missing_ok=True)
            audio.unlink(missing_ok=True)
        progress(f"已唤醒：{recognized}")
        if not command:
            if args.speak:
                speak("我在，请说。")
            progress(f"请说指令，等待停顿后识别（最长 {args.seconds:g} 秒）…")
            audio = record_until_pause(
                start_timeout=args.wake_window,
                max_seconds=args.seconds,
                pause_seconds=args.command_pause_seconds,
                min_rms=args.wake_min_rms,
            )
            if audio is None:
                progress("未听到指令，继续监听唤醒词。")
                continue
            try:
                progress("指令录音结束，正在请求在线语音识别…")
                command = transcribe_qwen(audio, model)
            finally:
                audio.unlink(missing_ok=True)
        if not command.strip():
            progress("未识别到指令，继续监听唤醒词。")
            continue
        _process_command(command, args, progress)
        if args.wake_once:
            return
        progress(f"任务已提交，继续监听唤醒词“{WAKE_PHRASE}”…")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RoboCup 人机交互与具身大脑原型")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="直接输入文本指令")
    source.add_argument("--audio", type=Path, help="音频文件路径")
    source.add_argument("--mic", action="store_true", help="从麦克风录音")
    source.add_argument("--wake", action="store_true", help="持续监听“豆包豆包”后接收指令")
    source.add_argument("--result", type=Path, help="执行层反馈 JSON 文件")
    parser.add_argument("--planner", choices=("rules", "llm"), default=None)
    parser.add_argument("--asr-provider", choices=("whisper", "qwen"), default=None)
    parser.add_argument("--asr-model", default=None)
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--wake-window", type=float, default=WAKE_DEFAULTS["wake_window"], help="等待开始说话的最长秒数")
    parser.add_argument("--wake-max-seconds", type=float, default=WAKE_DEFAULTS["wake_max_seconds"], help="唤醒词与同句指令的最长录音秒数")
    parser.add_argument("--pause-seconds", type=float, default=WAKE_DEFAULTS["pause_seconds"], help="判定说完话的连续静音秒数")
    parser.add_argument("--command-pause-seconds", type=float, default=WAKE_DEFAULTS["command_pause_seconds"], help="唤醒后单独说指令时的连续静音秒数")
    parser.add_argument("--wake-min-rms", type=float, default=WAKE_DEFAULTS["wake_min_rms"], help="判断是否正在说话的音量阈值")
    parser.add_argument("--wake-once", action="store_true", help="处理一条唤醒后的指令即退出")
    parser.add_argument("--speak", action=argparse.BooleanOptionalAction, default=None, help="播报反馈或需澄清提示")
    args = parser.parse_args(argv)
    if args.planner is None:
        args.planner = WAKE_DEFAULTS["planner"] if args.wake else "rules"
    if args.seconds is None:
        args.seconds = WAKE_DEFAULTS["seconds"] if args.wake else 5.0
    if args.speak is None:
        args.speak = WAKE_DEFAULTS["speak"] if args.wake else False
    return args


def main() -> int:
    args = parse_args()
    def progress(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    try:
        if args.wake:
            _run_wake_mode(args, progress)
            return 0
        if args.result:
            result = json.loads(args.result.read_text(encoding="utf-8"))
            message = feedback_text(result)
            print(json.dumps({"feedback": message}, ensure_ascii=False, indent=2))
            if args.speak:
                from .speech import speak
                progress("正在语音播报反馈…")
                speak(message)
                progress("语音播报调用完成。")
            return 0
        audio = None
        if args.mic:
            from .speech import record_microphone
            progress(f"开始录音 {args.seconds:g} 秒，请现在说话…")
            audio = record_microphone(args.seconds)
            progress(f"录音完成：{audio}")
        elif args.audio:
            audio = args.audio
        if audio:
            if args.asr_provider == "qwen":
                from .speech import transcribe_qwen

                progress("录音完成，正在请求在线语音识别模型…")
                text = transcribe_qwen(audio, args.asr_model or "qwen3-asr-flash")
            else:
                from .speech import transcribe

                text = transcribe(audio, args.asr_model or "small", progress=progress)
        else:
            text = args.text
        _process_command(text, args, progress)
        return 0
    except KeyboardInterrupt:
        progress("已停止监听。")
        return 0
    except (OSError, ValueError, KeyError, IndexError, ImportError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
