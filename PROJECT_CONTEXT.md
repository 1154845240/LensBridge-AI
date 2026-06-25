# LensBridge AI 项目上下文

## 产品定位

LensBridge AI（镜桥 AI）是 Windows 跨端屏幕分析助手：

1. 电脑端静默选择并截取屏幕区域。
2. 本地 FastAPI 服务接收图片或文字。
3. 多模态模型生成答案。
4. 桌面、手机或第二屏通过网页实时查看同一结果。

正式用户只需运行单文件 `LensBridgeAI.exe`，无需安装 Python 或依赖；真实分析需自行配置 API Key。

## 当前架构

```text
launcher.py                 单进程入口、日志、单实例、优雅退出
app_paths.py                源码/打包运行路径与数据迁移
runtime_state.py            快捷键通知和截图状态
client/client.py            鼠标、键盘、截图、上传
server/app.py               FastAPI、会话、配置、SSE、任务协调
server/agent_manager.py     OpenAI 兼容模型调用
server/database.py          SQLite 数据访问
server/file_cleanup.py      上传图片解析、级联删除与孤儿清理
server/templates/index.html 桌面与移动端页面
LensBridgeAI.spec           PyInstaller 单文件构建
dist/LensBridgeAI.exe       可分发程序
```

## 运行数据

打包后位于 `%LOCALAPPDATA%\LensBridgeAI`：

```text
config.json
server.db
uploads/
temp/
logs/lensbridge.log
```

源码模式使用项目中的 `server/config.json`、`server/server.db`、`server/uploads` 和 `temp_captures`。

服务启动时会清理上传目录中未被数据库引用的孤儿图片；删除会话、题目或全部历史时同步删除关联图片。

## 数据库

### conversations

| 字段 | 说明 |
|---|---|
| id | 主键 |
| title | 对话名称 |
| created_at | UTC 创建时间 |

### captures

| 字段 | 说明 |
|---|---|
| id | 主键 |
| conversation_id | 外键，关联 conversations |
| timestamp | UTC 创建时间 |
| image_filename | 单文件名或 JSON 文件名数组 |
| user_prompt | 文字问题 |
| agent_name | 生成该答案的 Agent ID |
| ai_response | Markdown 答案 |
| status | pending / processing / completed / failed |

删除对话时级联删除记录，并清理对应图片。

## 配置

`config.json` 包含：

- `active_agent`：后续新题使用的 Agent ID。
- `agents`：显示别名、API Key、模型名、API URL。
- `global_system_prompt`：全局系统提示词。
- `server`：监听地址和端口。
- `hotkeys`：模式、发送、清空、重试、打开页面。

默认快捷键：

| 功能 | 按键 |
|---|---|
| 单图/多图切换 | F8 |
| 发送多图队列 | F9 |
| 清空队列 | Esc |
| 重新分析最新题 | F10 |
| 打开本机页面 | F12 |

支持 `Alt+Q`、`Ctrl+W` 等组合键并实时生效。

## 已确认的关键结论

- 单图模式截图后立即上传；多图模式先进入队列。
- 鼠标左键长按 3 秒记录起点，15 秒内再次长按记录终点。
- 页面显示模式、队列、倒计时和操作状态。
- 同一 capture 只有一个后台模型生成任务，多端答案一致。
- SSE 客户端只读取数据库中的统一增量结果。
- 模型切换只影响后续新题；旧答案保留真实模型。
- 重新分析使用当前模型。
- API Key 输入框已降低 Chrome 密码保存识别概率。
- 页面模型标签使用 Agent 的 `display_name`，不显示内部 ID。
- SQLite UTC 时间在前端转换为本地时间。
- 页面仅保留顶部电源按钮作为退出入口。
