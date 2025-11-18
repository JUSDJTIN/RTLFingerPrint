# rtl_fingerprint/patterns/queue.py
from typing import Optional
from .base import PatternBase
from ..ir import SignalIR, Expr
from ..compiler_types import Fingerprint

class QueuePattern(PatternBase):
    """
    toy：识别 mshr_full = (mshr_used == const)
    """
    def extract(self, sig: SignalIR, expr: Expr) -> Optional[Fingerprint]:
        if expr is None or expr.op != "eq":
            return None
        lhs, rhs = expr.args
        if lhs != "mshr_used":
            return None
        if not isinstance(rhs, int):
            return None
        cap = int(rhs)
        attrs = {
            "cap": cap,
            "hwm": cap - 1,
            "counter": "mshr_used"
        }
        return Fingerprint(
            ftype="Queue",
            path=sig.module_path,
            attrs=attrs,
            conf=0.95,
            impact=0.6
        )

