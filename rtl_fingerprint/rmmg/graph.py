# rtl_fingerprint/rmmg/graph.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class RmmgNode:
    def __init__(self, node_id: int, hier_name: str, kind: str, width: int, uhdm_obj=None):
        self.id = node_id
        self.hier_name = hier_name
        self.kind = kind          # "input" / "output" / "net" / "reg" / "memory" ...
        self.width = width        # -1 表示未知
        self.uhdm_obj = uhdm_obj
        self.attrs: Dict[str, Any] = {}  # module_path / signal_name / is_arch_visible / is_micro_state 等

class RmmgEdge:
    def __init__(self, src, dst, is_seq=False, cond=None, src_loc=None):
        self.src = src
        self.dst = dst
        self.is_seq = is_seq
        self.cond = cond
        self.src_loc = src_loc

class RmmgGraph:
    def __init__(self):
        self.nodes: Dict[int, RmmgNode] = {}
        self.name_to_id: Dict[str, int] = {}
        self.edges = []  # {src, dst, is_seq, cond, src_loc}

    # 根据 hier_name 获取 / 创建节点
    def get_node_id(self, hier_name: str) -> Optional[int]:
        return self.name_to_id.get(hier_name)

    def add_node(self, hier_name: str, kind: str, width: int,
                 uhdm_obj=None) -> int:
        node_id = self.name_to_id.get(hier_name)
        if node_id is not None:
            return node_id
        node_id = len(self.nodes)
        node = RmmgNode(node_id, hier_name, kind, width, uhdm_obj)
        self.nodes[node_id] = node
        self.name_to_id[hier_name] = node_id
        return node_id

    def add_edge(self, src_id, dst_id, is_seq=False, cond=None, src_loc=None):
        edge = RmmgEdge(src_id, dst_id, is_seq=is_seq, cond=cond, src_loc=src_loc)
        self.edges.append(edge)

    def summary(self) -> str:
        return f"RMMG: {len(self.nodes)} nodes, {len(self.edges)} edges"
