# rtl_fingerprint/patterns/__init__.py
from typing import Optional
from .mapping import MappingPattern
from .queue import QueuePattern
from .prediction import PredictionPattern
from .arbiter import ArbiterPattern
from ..ir import SignalIR, Expr
from ..compiler_types import Fingerprint


class PatternExtractor:
    """
    顶层 Pattern 提取器：
      根据 mech 调用不同模式识别。
    """

    def __init__(self):
        self.mapping = MappingPattern()
        self.queue = QueuePattern()
        self.prediction = PredictionPattern()
        self.arbiter = ArbiterPattern()

    def extract_for_mech(self, mech: str, sig: SignalIR, expr: Expr) -> Optional[Fingerprint]:
        if mech == "mapping":
            return self.mapping.extract(sig, expr)
        if mech == "queue":
            return self.queue.extract(sig, expr)
        if mech == "prediction":
            return self.prediction.extract(sig, expr)
        if mech == "arbiter":
            return self.arbiter.extract(sig, expr)
        return None

