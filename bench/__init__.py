"""MCPSentry 基准执行（成员 B 交付，规格由 A 出：docs/基准规格.md）。

    python -m bench matrix --out bench/results          # 120 组
    python -m bench normal --out bench/results          # 50 条正常任务（误报）
    python -m bench replay --out bench/results --sample 12
    python -m bench single --target T1 --class A2_indirect_tool_result --seed 42 --defense on
    python -m bench summary --out bench/results         # 调 engine.analysis 复算指标
"""
