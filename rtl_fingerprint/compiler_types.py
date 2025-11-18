# rtl_fingerprint/compiler_types.py
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Fingerprint:
    ftype: str
    path: str
    attrs: Dict[str, Any]
    conf: float = 0.8
    impact: float = 0.5

@dataclass
class Witness:
    fp_type: str
    path: str
    params: Dict[str, Any]

