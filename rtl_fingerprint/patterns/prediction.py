# rtl_fingerprint/patterns/prediction.py
from typing import Optional
from .base import PatternBase
from ..ir import SignalIR, Expr
from ..compiler_types import Fingerprint


class PredictionPattern(PatternBase):
    """
    预测/暂态指纹 stub：
      - 后续可识别 ghist 宽度、pht_index = pc ^ ghist 等。
    """

    def extract(self, sig: SignalIR, expr: Expr) -> Optional[Fingerprint]:
        # TODO: 实现 BPU/PHT/BTB/RSB 模式识别
        return None

