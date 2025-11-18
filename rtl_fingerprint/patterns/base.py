# rtl_fingerprint/patterns/base.py
from abc import ABC, abstractmethod
from typing import Optional
from ..ir import SignalIR, Expr
from ..compiler_types import Fingerprint


class PatternBase(ABC):
    @abstractmethod
    def extract(self, sig: SignalIR, expr: Expr) -> Optional[Fingerprint]:
        """从信号及其表达式中抽取指纹（若匹配则返回 Fingerprint，否则 None）。"""
        raise NotImplementedError

