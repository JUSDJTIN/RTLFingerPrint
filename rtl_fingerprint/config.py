# rtl_fingerprint/config.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import yaml


@dataclass
class Config:
    rtl_filelist: str
    top_module: str
    defines: List[str]
    analysis: Dict[str, Any]
    observability: Dict[str, Any]
    frontend: str = "toy"  # "toy" or "uhdm"
    arch_visible_rules: List[Dict[str, Any]] = field(default_factory=list)
    uhdm_database: Optional[str] = None


def load_config(path: str) -> Config:
    with open(path) as f:
        cfg_raw = yaml.safe_load(f)
    rtl_cfg = cfg_raw["rtl"]
    rtl_target = cfg_raw["targets"]
    return Config(
        rtl_filelist=rtl_cfg["filelist"],
        top_module=rtl_cfg["top_module"],
        defines=rtl_cfg.get("defines", []),
        analysis=rtl_target,
        observability=cfg_raw.get("observability", {}),
        frontend=cfg_raw.get("frontend", "toy"),
        arch_visible_rules=rtl_target.get("arch_visible_rules",[]),
        uhdm_database=rtl_cfg.get("uhdm_database"),
    )

