# rtl_fingerprint/ir.py
from dataclasses import dataclass
from typing import Any, List, Optional
import fnmatch

class Expr:
    """简单表达式 IR，用于模式识别和后续扩展."""
    def __init__(self, op: str, args: List[Any]):
        self.op = op
        self.args = args

    def __repr__(self) -> str:
        return f"Expr({self.op}, {self.args})"

@dataclass
class SignalIR:
    name: str
    expr: Optional[Expr]
    module_path: str

@dataclass
class RTLIR:
    signals: List[SignalIR]

    def find_signals(self, name_patterns: List[str]) -> List[SignalIR]:
        res = []
        for s in self.signals:
            if any(fnmatch.fnmatch(s.name, pat) for pat in name_patterns):
                res.append(s)
        return res

    def get_expr(self, sig: SignalIR) -> Optional[Expr]:
        return sig.expr

