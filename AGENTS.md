# LensBridge AI 协作规则

## 开始工作

后续开发前按顺序阅读：

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `TODO.md`
4. `CHANGELOG.md`

这四个文件是项目的唯一权威交接文档。

## 开发约束

- 默认目标平台是 Windows。
- 保持现有 Python、FastAPI、SQLite、原生 HTML/JS 架构，除非用户明确要求重构。
- 正式入口是 `launcher.py`；`run_all.bat` 仅用于源码调试。
- 正式产物是无控制台、无托盘的单文件 `dist/LensBridgeAI.exe`。
- 不提交、展示或写入真实 API Key；`server/config.default.json` 必须保持无密钥。
- 不删除或覆盖用户的 `config.json`、`server.db`、截图和日志。
- 修改数据库结构时必须提供兼容迁移。
- 修改页面后必须检查桌面端和移动端。
- 修改快捷键时必须保持单键、组合键和实时生效能力。

## 关键行为

- 每条截图或文本记录固定绑定创建时的 Agent ID。
- 已完成答案显示实际生成它的模型别名，不随右上角选择变化。
- “重新分析”使用当前选中的 Agent，并更新该记录的 Agent。
- 多个浏览器只订阅同一个后台生成任务，不得重复调用模型。
- Agent 内部 ID 用于持久化；界面只显示 `display_name`。
- 数据库时间是 UTC；前端负责转换为浏览器本地时间。
- 本机页面固定为 `http://127.0.0.1:8000/view`；默认 `F12` 打开。
- 关闭接口仅允许本机调用。

## 修改与验证

- 编辑文件使用 `apply_patch`。
- Python 修改后运行编译检查。
- 前端修改后检查内联 JavaScript 语法。
- 模型流修改后运行：

```powershell
.venv\Scripts\python -m server.test_stream_consistency
```

- 构建前先通过页面关闭正在运行的旧 EXE，否则 Windows 会锁定文件。
- 构建命令：

```powershell
.venv\Scripts\python -m PyInstaller --noconfirm --clean LensBridgeAI.spec
```

- 构建后至少验证启动、`/system/status`、页面加载、模型流和安全退出。

