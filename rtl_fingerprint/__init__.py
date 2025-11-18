# rtl_fingerprint/__init__.py

"""
RTL Fingerprint Compiler

- 从复杂处理器 RTL（如 Chipyard/BOOM）中自动抽取微架构“指纹”
- 输出：
    - fingerprints.json
    - constraints.smt2
    - params.yml
    - witness.csv
    - ablation.cfg
"""

__all__ = [
    "config",
    "ir",
    "compiler_types",
    "targets",
    "slicing",
    "constraints",
    "ablation",
    "compiler",
    "cli",
]

