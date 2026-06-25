# LensBridge AI

LensBridge AI（镜桥 AI）是一款面向 Windows 的跨端屏幕分析助手。它可以截取电脑屏幕区域，将图片或文字发送给多模态模型，并在电脑、手机或第二块屏幕的浏览器中实时查看回答。

## 主要功能

- 鼠标长按选择屏幕区域并自动截图分析
- 支持单图模式和多图队列模式
- 支持 Gemini、豆包及其他 OpenAI 兼容接口
- 支持新增、编辑、删除和切换多个 Agent
- 桌面端和移动端实时同步回答
- Markdown、代码高亮和 SQL 自动格式化
- 会话历史、重新分析和模型来源记录
- 可构建为无需安装 Python 的单文件 Windows 程序

## 技术栈

- Python
- FastAPI
- SQLite
- 原生 HTML、CSS、JavaScript
- PyInstaller

## 源码运行

建议使用 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r server\requirements.txt
pip install -r client\requirements.txt
python launcher.py
```

也可以在 Windows 中运行：

```powershell
run_all.bat
```

启动后访问：

```text
http://127.0.0.1:8000/view
```

首次运行后，在网页设置中添加模型名称、API URL、模型 ID 和 API Key。

## 默认快捷键

| 功能 | 快捷键 |
|---|---|
| 切换单图/多图模式 | `F8` |
| 发送多图队列 | `F9` |
| 清空队列 | `Esc` |
| 重新分析最新题目 | `F10` |
| 打开本机页面 | `F12` |

快捷键可以在网页设置中修改，并支持组合键。

## 截图方式

1. 长按鼠标左键 3 秒，记录截图起点。
2. 在 15 秒内再次长按鼠标左键 3 秒，记录截图终点。
3. 程序自动截取区域并发送给当前选中的 Agent。

## 构建 Windows EXE

```powershell
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean LensBridgeAI.spec
```

构建结果位于：

```text
dist/LensBridgeAI.exe
```

构建前请先退出正在运行的旧版程序，避免 Windows 锁定 EXE 文件。

## 运行数据

打包程序会将用户数据保存在：

```text
%LOCALAPPDATA%\LensBridgeAI
```

其中包括：

```text
config.json
server.db
uploads/
temp/
logs/
```

删除 EXE 不会自动删除这些用户数据。如需完全清理，可以在退出程序后手动删除上述目录。

## 安全说明

- 不要将真实 API Key 写入代码或提交到 Git。
- `server/config.json`、数据库、截图、日志、缓存和构建产物已通过 `.gitignore` 排除。
- 仓库中的 `server/config.default.json` 不包含任何密钥。
- 服务启动时会自动清理数据库未引用的孤儿上传图片。
- 删除会话、单条题目或全部历史时，会同步删除对应图片。

## 项目结构

```text
launcher.py                  单进程正式入口
app_paths.py                 开发/打包运行路径管理
runtime_state.py             截图服务状态与退出控制
client/client.py             鼠标、键盘、截图和上传
server/app.py                FastAPI 服务和任务协调
server/agent_manager.py      模型接口调用
server/database.py           SQLite 数据访问
server/file_cleanup.py       上传图片与孤儿文件清理
server/templates/index.html  桌面端和移动端页面
LensBridgeAI.spec            PyInstaller 构建配置
```

## 开发验证

模型流相关修改后运行：

```powershell
.\.venv\Scripts\python -m server.test_stream_consistency
.\.venv\Scripts\python -m server.test_file_cleanup
```
