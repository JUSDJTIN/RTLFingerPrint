# rtl_fingerprint/patterns/arbiter.py
from typing import Optional
from .base import PatternBase
from ..ir import SignalIR, Expr
from ..compiler_types import Fingerprint


class ArbiterPattern(PatternBase):
    """
    仲裁/共享资源指纹 stub：
      - 后续可识别 RR/PRI/TDMA 等策略。
    """

    def extract(self, sig: SignalIR, expr: Expr) -> Optional[Fingerprint]:
        # TODO: 实现 TLXbar / MemoryBus 仲裁识别
        return None

