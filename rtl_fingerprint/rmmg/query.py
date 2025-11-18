# rtl_fingerprint/rmmg/query.py

from __future__ import annotations
from collections import deque, defaultdict
from typing import Callable, Iterable, List, Dict, Tuple, Optional

from .graph import RmmgGraph, RmmgNode, RmmgEdge


NodePred = Callable[[RmmgNode], bool]


class RmmgQueryEngine:
    """
    针对 RmmgGraph 的通用查询引擎：
      - 按谓词筛选源/汇节点
      - 在依赖图上做 BFS/DFS 找路径
      - 封装若干“常用安全问题”的查询（例如 MSHR → ROB commit）
    """

    def __init__(self, graph: RmmgGraph):
        self.graph = graph
        self._adj = None  # 延迟构建邻接表

    # ===== 公共基础方法 =====================================================

    def find_nodes(self, pred: NodePred) -> List[int]:
        """按谓词筛选节点，返回节点 ID 列表。"""
        return [nid for nid, node in self.graph.nodes.items() if pred(node)]

    def build_adj_list(self) -> Dict[int, List[int]]:
        """构建一次 src→dst 的邻接表，供多次查询复用。"""
        if self._adj is not None:
            return self._adj
        adj: Dict[int, List[int]] = defaultdict(list)
        for e in self.graph.edges:
            adj[e.src].append(e.dst)
        self._adj = adj
        return adj

    def bfs_paths(
        self,
        sources: Iterable[int],
        targets: Iterable[int],
        max_depth: int = 50,
        max_paths: Optional[int] = None,
    ) -> List[List[int]]:
        """
        多源 BFS，寻找从 sources 到 targets 的有向路径。
        - sources / targets: 节点 ID 集合
        - max_depth: 限制路径最大长度，防止在大图中无限扩散
        - max_paths: 最多返回多少条路径（None 表示不限）
        返回: 每条路径是一个 node_id 列表
        """
        adj = self.build_adj_list()
        target_set = set(targets)
        found_paths: List[List[int]] = []

        # 初始化队列
        q = deque()
        for s in sources:
            q.append((s, [s]))

        visited = set(sources)

        while q:
            cur, path = q.popleft()
            if max_paths is not None and len(found_paths) >= max_paths:
                break

            if len(path) > max_depth:
                continue

            if cur in target_set:
                found_paths.append(path)
                # 如果只关心最短距离，可以在这里不扩展该节点
                # continue
                # 这里选择仍然允许找到其它源→该目标的路径
                continue

            for nxt in adj.get(cur, []):
                if nxt not in visited:
                    visited.add(nxt)
                    q.append((nxt, path + [nxt]))

        return found_paths

    def pretty_print_paths(
        self,
        paths: List[List[int]],
        max_paths: int = 5,
        show_width: bool = True,
        show_kind: bool = True,
    ) -> None:
        """简易打印路径，方便调试和人工检查。"""
        if not paths:
            print("[RMMG-QUERY] No paths found.")
            return

        for idx, p in enumerate(paths[:max_paths]):
            print(f"[PATH #{idx}] length={len(p)}")
            for nid in p:
                n = self.graph.nodes[nid]
                extra = []
                if show_kind:
                    extra.append(f"kind={n.kind}")
                if show_width:
                    extra.append(f"w={n.width}")
                extra_str = " ".join(extra)
                print(f"  {nid:6d}  {n.hier_name}  {extra_str}")
            print()

    # ===== 一些常见谓词封装 ================================================

    @staticmethod
    def pred_hier_contains(substr: str) -> NodePred:
        """返回一个谓词：hier_name 包含给定子串。"""
        def _pred(node: RmmgNode) -> bool:
            return substr in node.hier_name
        return _pred

    @staticmethod
    def pred_hier_startswith(prefix: str) -> NodePred:
        """返回一个谓词：hier_name 以 prefix 开头。"""
        def _pred(node: RmmgNode) -> bool:
            return node.hier_name.startswith(prefix)
        return _pred

    @staticmethod
    def pred_arch_visible() -> NodePred:
        """返回一个谓词：节点被标记为架构可见。"""
        def _pred(node: RmmgNode) -> bool:
            return bool(node.attrs.get("is_arch_visible", False))
        return _pred
    @staticmethod
    def pred_name_contains(substr: str) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            return substr in n.hier_name
        return _p

    @staticmethod
    def pred_name_regex(pattern: str) -> NodePred:
        pat = re.compile(pattern)
        def _p(n: RmmgNode) -> bool:
            return bool(pat.search(n.hier_name))
        return _p

    @staticmethod
    def pred_arch_visible() -> NodePred:
        def _p(n: RmmgNode) -> bool:
            return bool(n.attrs.get("is_arch_visible", False))
        return _p

    # 常用语义 predicate
    def pred_mshr_meta(self) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            name = n.hier_name
            return ("MSHR.meta_" in name) or ("MSHR.request_" in name)
        return _p

    def pred_rob_commit_any(self) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            name = n.hier_name
            return ("io_commit_" in name) and bool(n.attrs.get("is_arch_visible", False))
        return _p

    # 示范：DCache load resp → ROB commit data
    def pred_dcache_resp_data(self) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            name = n.hier_name
            return ("dcache" in name and "io_lsu_resp" in name and "bits_data" in name)
        return _p

    def pred_rob_commit_wdata(self) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            name = n.hier_name
            return ("Rob.io_commit_uops_0" in name and ("data" in name or "wdata" in name))
        return _p

    # ===== 具体目标 1：MSHR meta → ROB commit ===============================

    def pred_mshr_meta(self) -> NodePred:
        """
        MSHR 元数据节点：
          - 名字包含 'MSHR.meta_' 或 'MSHR.request_'
        根据你实际 MSHR 命名习惯可以再细化，例如只收 tag/state/way。
        """
        def _pred(node: RmmgNode) -> bool:
            name = node.hier_name
            return ("MSHR.meta_" in name) or ("MSHR.request_" in name)
        return _pred

    def pred_rob_commit_arch(self) -> NodePred:
        """
        ROB commit 输出节点：
          - hier_name 以 'work@Rob.io_commit_' 开头
          - 且 is_arch_visible == True（在 builder 里已标注）
        """
        def _pred(node: RmmgNode) -> bool:
            return node.hier_name.startswith("work@Rob.io_commit_") and \
                   bool(node.attrs.get("is_arch_visible", False))
        return _pred

    def query_mshr_to_rob_commit(
        self,
        max_depth: int = 60,
        max_paths: Optional[int] = 20,
    ) -> List[List[int]]:
        """
        查询：MSHR 元数据信号是否能通过某条路径影响 ROB commit 流。
        返回：每条路径是 node_id 列表。
        """
        src_nodes = self.find_nodes(self.pred_mshr_meta())
        dst_nodes = self.find_nodes(self.pred_rob_commit_arch())

        print(f"[RMMG-QUERY] MSHR meta sources: {len(src_nodes)}")
        print(f"[RMMG-QUERY] ROB commit targets: {len(dst_nodes)}")

        if not src_nodes or not dst_nodes:
            return []

        paths = self.bfs_paths(
            sources=src_nodes,
            targets=dst_nodes,
            max_depth=max_depth,
            max_paths=max_paths,
        )

        print(f"[RMMG-QUERY] Found {len(paths)} paths from MSHR meta to ROB commit.")
        return paths

    def pred_dcache_resp_data(self) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            return "dcache.io_lsu_resp_0_bits_data" in n.hier_name
        return _p

    def pred_rob_commit_wdata(self) -> NodePred:
        def _p(n: RmmgNode) -> bool:
            return "Rob.io_commit_uops_0" in n.hier_name and "data" in n.hier_name
        return _p
    
    def query_dcache_to_rob_data(self, max_depth=100, max_paths=20):
        src = self.find_nodes(self.pred_dcache_resp_data())
        dst = self.find_nodes(self.pred_rob_commit_wdata())
        print(f"[RMMG-QUERY] DCache resp sources: {len(src)}")
        print(f"[RMMG-QUERY] ROB commit data targets: {len(dst)}")
        return self.bfs_paths(src, dst, max_depth=max_depth, max_paths=max_paths)


    # ===== 扩展接口：自定义源/汇谓词 =======================================

    def query_custom(
        self,
        source_pred: NodePred,
        target_pred: NodePred,
        max_depth: int = 50,
        max_paths: Optional[int] = None,
    ) -> List[List[int]]:
        """
        通用版本：使用自定义源/汇谓词做路径查询。
        例：
          engine.query_custom(
              engine.pred_hier_contains("io_csr_satp"),
              engine.pred_hier_contains("dcache.tags"),
              max_depth=80
          )
        """
        src_nodes = self.find_nodes(source_pred)
        dst_nodes = self.find_nodes(target_pred)

        print(f"[RMMG-QUERY] custom sources: {len(src_nodes)}")
        print(f"[RMMG-QUERY] custom targets: {len(dst_nodes)}")

        if not src_nodes or not dst_nodes:
            return []

        paths = self.bfs_paths(
            sources=src_nodes,
            targets=dst_nodes,
            max_depth=max_depth,
            max_paths=max_paths,
        )

        print(f"[RMMG-QUERY] Found {len(paths)} paths for custom query.")
        return paths

