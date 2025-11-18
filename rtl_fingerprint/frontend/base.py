# rtl_fingerprint/frontend/base.py
from abc import ABC, abstractmethod
from typing import Any
from ..config import Config
from ..ir import RTLIR


class FrontendBase(ABC):
    """RTL 前端抽象接口：负责从 RTL 文件生成 RTLIR。"""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    @abstractmethod
    def parse(self) -> RTLIR:
        """解析 RTL 工程，返回 RTLIR。"""
        raise NotImplementedError

