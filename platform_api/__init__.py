"""platform_api/ — 评测平台后端（成员 B）。

包名不叫 `platform`：技术栈文档 §8 写的是 `platform/`，但那个名字会遮蔽标准库
`platform` 模块（仓库根在 sys.path 上时，`pydantic.version.version_info()` 直接
AttributeError，uvicorn/server.py 也 import 它）。目录职责不变，只改可导入的名字。

四件事，对应技术栈与分工文档 §6 对 B 的要求：

- 运行编排（`orchestr.py`，FastAPI BackgroundTasks，MVP 不上 Celery）
- 报告服务（`app.py`，读 bench/results 下的原始产物，不重新计算任何判定）
- 运行历史（`history.py`，SQLite）
- 报告导出（`export.py`，JSON / Markdown / 自包含 HTML）

判定永远来自 engine 的 oracle，本层只做展示与编排——D12 的纪律是"只修部署不动引擎"，
所以这里不允许出现第二套安全逻辑。

    python -m platform_api serve --host 0.0.0.0 --port 8000
    python -m platform_api build-demo
"""
