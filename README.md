# RoboCup 前两层原型

覆盖图中的 **人机交互层**（录音、ASR、TTS）和 **具身大脑层**（指令理解、任务规划、任务结果反馈）。第三层及以下由后续模块实现；本项目用 JSON 作为临时对接边界。当前包含一个规则规划器用于离线联调，以及可选的 OpenAI 兼容 Chat Completions 接口用于 LLM 规划。

## 立即运行

在项目目录执行：

```powershell
python -m brain_frontend --text "去客厅找一个水瓶，找到之后告诉我"
python -m unittest discover -s tests -v
```

程序打印两份 JSON：`utterance` 为识别或输入的文字，`plan` 为待执行任务。默认规则规划器只覆盖 Demo 指令，未知指令返回 `needs_clarification`，不会猜测机器人动作。

## 语音输入与输出

Windows 上验证完整的“麦克风 → ASR → LLM 任务计划”可使用在线 ASR，以避开本地 `faster-whisper` 在部分电脑上的原生库加载问题。先配置好同地域的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`；例如新加坡的普通 Key 使用 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`。然后运行：

```powershell
python -m pip install -r requirements-windows-online.txt
python -m brain_frontend --mic --seconds 5 --asr-provider qwen --planner llm --speak
```

录音在 Windows 本机完成；音频会发送给百炼 `qwen3-asr-flash` 识别，再将文字发送给当前配置的 LLM 规划。在线 ASR 和 LLM 可能产生调用费用。`--speak` 在计划生成后播报“任务计划已生成”，执行完成的真实结果仍需由执行层反馈。已有 WAV 文件也可以用 `--audio 路径 --asr-provider qwen --planner llm` 测试。这个路径无需安装或加载 faster-whisper。

### “豆包豆包”唤醒

在已经配置好新加坡地域的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 的同一个 PowerShell 窗口运行：

```powershell
python -m brain_frontend --wake
```

说“豆包豆包”，听到“我在，请说”后，再说任务指令；也可以连续说“豆包豆包，去客厅找一个水瓶，找到之后告诉我”，程序会等明显停顿后才识别整句话。“豆包，豆包”也能识别为唤醒词。处理完成后继续监听；按 `Ctrl+C` 结束。仅测试一条指令可追加 `--wake-once`。唤醒模式已内置在线 Qwen ASR、`llm` 规划、语音播报和下述录音参数的默认值；如需临时关闭播报，可加 `--no-speak`。API Key、服务地域地址和模型配置仍从环境变量读取，不写入代码。

`--wake-window 3` 表示等待开始说话最多 3 秒，说话开始后不会按 3 秒截断。`--pause-seconds 1.5` 控制唤醒词与同句指令的停顿判断，语速较慢时可调成 `2`。唤醒后单独说指令使用较短的 `--command-pause-seconds 0.8`，说完后通常约 0.8 秒即结束录音；若句中短暂停顿导致截断，可调成 `1.2`。`--wake-max-seconds 15` 和 `--seconds 8` 分别是两种录音的安全上限，并非固定等待时间。最长可设为 30 秒。

目前这是基于分段录音和在线 ASR 的原型唤醒：明显静音的录音段会跳过，但有声音的录音段会上传识别，可能产生费用；在线识别期间不能同时监听，所以唤醒词后请稍等提示再说指令。终端会显示每段语音的识别文字，方便判断是否正确识别了“豆包豆包”；若输出为空或是其他字词，唤醒不会触发。噪声较大时可调整 `--wake-min-rms`（默认 100）；若太高导致漏检，可降低该值。它还不是离线、低延迟的专用唤醒词模型。

唤醒识别优先使用整段录音开头的 3 秒；只有确认唤醒后，才会对超过 3 秒的完整录音再做一次识别，以获取没有被截断的指令。若开头 3 秒依然显示“嗯”或其他文字，说明在线 ASR 没有转写出唤醒词；此时不会执行普通指令。长句唤醒成功时会多产生一次在线 ASR 调用。

本地 Whisper 路径仍保留，供后续 Ubuntu 或兼容的 Windows 环境使用：

```powershell
python -m pip install -r requirements-speech.txt
python -m brain_frontend --audio path/to/command.wav --asr-provider whisper
python -m brain_frontend --mic --asr-provider whisper --speak
```

`--mic` 会录制固定时长（默认 5 秒，`--seconds` 可改）；`--audio` 支持音频文件。第一次使用 faster-whisper 会下载所选模型，可用 `--asr-model` 指定模型名或本地模型路径。`--speak` 使用系统可用的 pyttsx3 语音引擎；如果语音引擎不可用，程序会报错，不会假装播报成功。

## LLM 规划

配置兼容 Chat Completions 的模型服务后运行：

```bash
export LLM_BASE_URL="http://localhost:11434/v1"
export LLM_MODEL="本地模型名称"
python3 -m brain_frontend --text "去客厅找一个水瓶，找到之后告诉我" --planner llm
```

需要鉴权时设置 `LLM_API_KEY`。模型的输出始终经过白名单、参数、地点和步骤依赖校验。模型服务地址和模型名仅是示例，需替换为实际服务配置。

在线服务示例：若选择阿里云百炼，在控制台创建 API Key 并查到业务空间的 Workspace ID；下面以北京地域的兼容接口为例，其他地域需换成对应地址。`qwen-plus` 是一个可用于联调的模型名；首次运行先确认账号可调用该模型。

```bash
export LLM_BASE_URL="https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
export LLM_MODEL="qwen-plus"
export LLM_ENABLE_THINKING="false"
read -srp 'API Key: ' LLM_API_KEY; echo; export LLM_API_KEY
python3 -m brain_frontend --text "去客厅找一个水瓶，找到之后告诉我" --planner llm
```

如果当前在 Windows PowerShell 开发机上验证，设置同样的配置变量，并从安全输入读取 Key：

```powershell
$env:LLM_BASE_URL = "https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
$env:LLM_MODEL = "qwen-plus"
$env:LLM_ENABLE_THINKING = "false"
$secureKey = Read-Host "API Key" -AsSecureString
$env:LLM_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
python -m brain_frontend --text "去客厅找一个水瓶，找到之后告诉我" --planner llm
```

`Read-Host "API Key"` 中的文字只是屏幕提示，不要把真实密钥放在双引号里；运行后在出现的输入提示处粘贴新密钥，输入不会回显。若出现 HTTP 401，先确认该 Key、业务空间 ID、地域与 Base URL 属于同一配置；套餐专属 Key 必须使用对应的专属地址。已经显示在截图或终端历史中的 Key 应立即停用并更换。

新版程序在 401 后尽量显示服务端错误码（不会输出完整响应或密钥）：`InvalidApiKey` 优先核对密钥及专属地址，`NOT AUTHORIZED` 优先核对业务空间 ID 与账号权限。可在 PowerShell 用 `if ([string]::IsNullOrWhiteSpace($env:LLM_API_KEY)) { '未设置' } else { '已设置' }` 检查当前终端是否保存了密钥，不要用 `echo $env:LLM_API_KEY`。

单句成功后，可执行 `python3 -m tests.online_smoke`（Windows 用 `python`）测试五条指令。该脚本会真实调用在线模型五次，可能产生费用；它检查合法任务、地点提取和未知任务拒绝，并打印各次耗时。

不要把真实 API Key 写入源文件或提交到版本库。`LLM_ENABLE_THINKING` 是部分兼容服务提供的扩展参数；如果服务不支持，取消该环境变量。

对于 Humble 的第一阶段联调，可先使用能稳定访问的在线 API；比赛或断网演示前，应在目标电脑上实测本地模型的响应时间与正确率。两者均通过同一个兼容接口接入，任务 JSON 不变。

## Ubuntu + ROS2 Humble

把本目录放在 `~/ros2_ws/src/brain_frontend`，然后在 Ubuntu 终端运行：

```bash
source /opt/ros/humble/setup.bash
cd ~/ros2_ws
colcon build --symlink-install --packages-select brain_frontend
source install/setup.bash
ros2 run brain_frontend brain_node --planner rules
```

另一个已 `source` ROS2 环境的终端可发送文本指令：

```bash
ros2 topic pub --once /brain/command_text std_msgs/msg/String '{data: "去客厅找一个水瓶，找到之后告诉我"}'
ros2 topic echo /brain/task_plan
```

安装 `requirements-speech.txt` 后，可运行 `ros2 run brain_frontend brain_node --mic --speak` 从麦克风输入并播报反馈。Humble 的 `rclpy` 来自系统 Python；安装语音依赖时应使用同一个 Python 环境，避免让 ROS2 节点运行在找不到 `rclpy` 的独立解释器里。

节点订阅 `/brain/command_text`（外部文字输入）和 `/brain/task_result`（执行反馈）；发布 `/brain/recognized_text`（实际送入规划器的文字）和 `/brain/task_plan`（JSON 任务计划）。目前使用 `std_msgs/String` 携带 JSON 便于组间先联调，接口稳定后可改成自定义 ROS2 消息。Windows 环境没有 ROS2 Humble，所以此节点尚需在 Ubuntu 实机验证。

## 与执行层的接口约定（v1）

`plan` 包含 `plan_id`、`source_text`、`steps`、`status`。每个步骤包含 `id`、`skill`、`args`、`depends_on`。允许的技能是 `navigate_to(location)`、`search_object(object, location?)`、`report_result(source_step)`、`return_home()`、`stop()`。地点暂定 `living_room`、`kitchen`，物体暂定 `bottle`。请与后端组员统一词表后修改 `brain_frontend/schema.py`。

执行层应逐步返回如下结果，并填入实际观测数据：

```json
{"plan_id":"...","step_id":"s2","status":"success","data":{"found":true,"object":"bottle","location":"living_room"}}
```

可用 `--result path/to/result.json --speak` 生成基于真实执行结果的语音反馈。`status` 为 `success`、`failed` 或 `cancelled`。`search_object` 的 `success` 只表示搜索流程正常结束；必须查看 `data.found` 才能说“找到”。

## 当前边界

本项目尚未连接 ROS2、Nav2 或视觉识别。`plan` 只是待执行请求，不代表机器人已完成任务。`stop` 应由将来的执行层直接取消当前任务。长期记忆、自由探索和自动重规划可以在基础闭环联调后加入。
