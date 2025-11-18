# rtl_fingerprint/rmmg/annotator.py

from __future__ import annotations
import re
from typing import Iterable, Dict, Any, List, Callable

from .graph import RmmgGraph, RmmgNode


RulePred = Callable[[str], bool]


def _build_arch_visible_predicates(rules: Iterable[Dict[str, Any]]) -> List[RulePred]:
    """
    将 config 中的 arch_visible_rules 解析成一组字符串谓词。
    规则格式示例：
      - {"type": "prefix", "value": "DigitalTop.tile_prci_domain.boom_tile.u_core.io_commit"}
      - {"type": "substr", "value": "tohost"}
      - {"type": "regex",  "value": ".*io_dmem_.*"}
    """
    preds: List[RulePred] = []

    for r in rules or []:
        rtype = r.get("type", "substr")
        val = r.get("value", "")
        if not val:
            continue

        if rtype == "prefix":
            def _p(name, v=val):
                return name.startswith(v)
            preds.append(_p)

        elif rtype == "regex":
            pat = re.compile(val)
            def _p(name, p=pat):
                return bool(p.search(name))
            preds.append(_p)

        else:  # 默认按 substr
            def _p(name, v=val):
                return v in name
            preds.append(_p)

    # 内置一些默认规则，防止 config 写空
    def _builtin_to_host(name: str) -> bool:
        return "tohost" in name or "auto_tohost" in name

    def _builtin_commit(name: str) -> bool:
        # ROB/IFU commit 相关
        return ("io_commit_" in name) or ("_rob_io_commit_" in name) or ("io_ifu_commit_" in name)

    def _builtin_mem(name: str) -> bool:
        # 主存接口、外设可见
        return ("io_mem_" in name) or ("axi4" in name and "_bits_addr" in name)

    preds.extend([_builtin_to_host, _builtin_commit, _builtin_mem])

    return preds


def annotate_basic_semantics(graph: RmmgGraph, arch_visible_rules: Iterable[Dict[str, Any]]) -> None:
    """
    基础语义标注：
      - 通过规则集标记架构可见节点 is_arch_visible
      - 暂时不在这里区分 micro_state / domain，只做最必要的染色
    """
    preds = _build_arch_visible_predicates(arch_visible_rules)

    for node in graph.nodes.values():
        name = node.hier_name
        is_arch = any(p(name) for p in preds)
        node.attrs["is_arch_visible"] = is_arch

