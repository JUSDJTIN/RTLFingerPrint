# rtl_fingerprint/targets.py
from typing import Dict, List
from .ir import RTLIR, SignalIR

class TargetSelector:
    def __init__(self, ir: RTLIR, analysis_cfg: dict):
        self.ir = ir
        self.cfg = analysis_cfg

    def select_targets(self) -> Dict[str, List[SignalIR]]:
        """
        返回: {"mapping":[SignalIR...], "queue":[...], ...}
        """
        targets: Dict[str, List[SignalIR]] = {}
        patterns = self.cfg.get("signal_patterns", {})

        for mech, pats in patterns.items():
            sigs = self.ir.find_signals(pats)
            targets[mech] = sigs
        return targets

