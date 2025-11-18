# rtl_fingerprint/patterns/mapping.py
from typing import Optional, Set, Dict, Any
from .base import PatternBase
from ..ir import SignalIR, Expr
from ..compiler_types import Fingerprint


class MappingPattern(PatternBase):
    """
    通用 L1/L2 映射指纹抽取：
      - 分析 index 表达式中涉及的地址位
      - 输出 line_size / sets / index_bits / xor_bits / addr_base
    """

    def extract(self, sig: SignalIR, expr: Expr) -> Optional[Fingerprint]:
        if expr is None:
            return None

        lin_info, non_linear = self._collect_linear_addr_bits(expr)
        if non_linear:
            # 暂不处理明显非线性映射，后续可以用统计方法补
            return None

        # 根据 base 名称优先级选择地址信号 (va > addr > paddr)
        base = None
        for cand in ["va", "addr", "paddr"]:
            if cand in lin_info:
                base = cand
                break
        if base is None:
            return None

        bits = lin_info[base]
        if not bits:
            return None

        lo = min(bits)
        hi = max(bits)

        line_size = 1 << lo
        sets = 1 << (hi - lo + 1)

        main_range = set(range(lo, hi + 1))
        xor_bits = sorted(list(bits - main_range))
        index_bits = sorted(list(main_range))

        attrs: Dict[str, Any] = {
            "line": line_size,
            "sets": sets,
            "index_bits": index_bits,
            "xor_bits": xor_bits,
            "addr_base": base,
            "ways": 1,
            "repl": "unknown",
        }
        conf = 0.85 if not xor_bits else 0.9
        impact = 0.7

        return Fingerprint(
            ftype="Mapping",
            path=sig.module_path,
            attrs=attrs,
            conf=conf,
            impact=impact,
        )

    # ---------- 内部：收集线性地址位 ---------- #

    def _collect_linear_addr_bits(self, expr: Expr) -> (Dict[str, Set[int]], bool):
        """
        返回 (lin_info, non_linear)
          lin_info: { "va": {bit_idx...}, "addr": {...} }
          non_linear: 是否检测到明显非线性运算
        """
        lin_info: Dict[str, Set[int]] = {}
        non_linear = False

        def add_bit(base: str, idx: int):
            lin_info.setdefault(base, set()).add(idx)

        def dfs(e: Expr):
            nonlocal non_linear
            if not isinstance(e, Expr):
                return

            op = e.op

            if op == "bit":
                base, idx = e.args
                if isinstance(idx, int):
                    add_bit(base, idx)
                else:
                    non_linear = True

            elif op == "slice":
                base, hi, lo = e.args
                if isinstance(hi, int) and isinstance(lo, int):
                    for i in range(lo, hi + 1):
                        add_bit(base, i)
                else:
                    non_linear = True

            elif op in ("xor", "concat"):
                for sub in e.args:
                    if isinstance(sub, Expr):
                        dfs(sub)
                    else:
                        if not isinstance(sub, int):
                            non_linear = True

            elif op == "replicate":
                subexpr, n = e.args
                if isinstance(subexpr, Expr) and isinstance(n, int):
                    dfs(subexpr)
                else:
                    non_linear = True

            elif op in ("add", "sub"):
                # 地址 + 常数 → 认为不改变 index 本质
                for sub in e.args:
                    if isinstance(sub, Expr):
                        dfs(sub)
            else:
                # 其他 op 暂视为潜在非线性
                non_linear = True

        dfs(expr)
        return lin_info, non_linear

