# rtl_fingerprint/ablation.py
from typing import List
from .compiler_types import Fingerprint

class AblationGenerator:
    def __init__(self):
        self.lines: List[str] = []

    def add_default(self, fps: List[Fingerprint]):
        # TODO: 可以根据 fp.path 分类生成更细致的开关
        self.lines.append("[L1D]")
        self.lines.append("REPL = FULL_ASSOC     ; or RANDOM")
        self.lines.append("")
        self.lines.append("[BP]")
        self.lines.append("BP_DISABLE = 1")
        self.lines.append("BP_STATIC  = TAKEN")
        self.lines.append("")
        self.lines.append("[QUEUE]")
        self.lines.append("MSHR_CAP = 32")
        self.lines.append("")

    def dump(self, path: str):
        with open(path, "w") as f:
            f.write("\n".join(self.lines))

