# rtl_fingerprint/frontend/chipyard.py
from .base import FrontendBase
from ..ir import RTLIR, SignalIR, Expr
from ..config import Config

# Pyverilog
from pyverilog.vparser.parser import parse
from pyverilog.vparser.ast import (
    Assign, Lvalue, Rvalue, Identifier, Pointer, Partselect,
    IntConst, UnaryOperator, BinaryOperator, Cond, Node
)

class ChipyardFrontend(FrontendBase):
    """
    基于 Pyverilog 的 Chipyard 前端（简化版）：
    - 解析 filelist 中的所有 Verilog
    - 在 AST 中查找指定名字的信号赋值
    - 把 RHS 表达式转换为内部 Expr 形式
    注意：
    - 实际 Chipyard 是 SystemVerilog + 生成代码，建议 long-term 用 Surelog/UHDM；
      这里作为一个 Python 可落地 demo。
    """

    def parse(self) -> RTLIR:
        # 解析 filelist：简单实现，可以从 filelist.f 读取所有 .v/.sv 文件名
        filelist = self._load_filelist(self.cfg.rtl_filelist)
        ast, _ = parse(filelist)

        # 收集 mapping/queue 相关的信号表达式（你可以按需拓展）
        signals: list[SignalIR] = []

        # 示例：我们想要：
        # - 任意模块里的 "*set_idx*" signal 的赋值 RHS
        # - 任意模块里的 "*mshr_full*" 的赋值 RHS
        target_name_patterns = ["*set_idx*", "*mshr_full*"]

        # 遍历 AST，找到 Assign/LHS，匹配名字，再抓 RHS
        for desc in ast.description.definitions:
            # desc: ModuleDef
            module_name = desc.name
            for item in desc.items:
                if isinstance(item, Assign):
                    l = item.left
                    r = item.right
                    sig_name = self._extract_name(l)
                    if sig_name and self._match_any(sig_name, target_name_patterns):
                        expr = self._convert_expr(r)
                        if expr is not None:
                            signals.append(
                                SignalIR(
                                    name=sig_name,
                                    expr=expr,
                                    module_path=module_name  # 简化：不带层次路径
                                )
                            )

        return RTLIR(signals=signals)

    # ---------- filelist 工具 ----------

    def _load_filelist(self, path: str):
        files = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 简化：只要不是 +define/–I 等选项，都认为是文件
                if line.startswith("+") or line.startswith("-"):
                    continue
                files.append(line)
        return files

    # ---------- 名字匹配 ----------

    def _match_any(self, name: str, patterns):
        import fnmatch
        return any(fnmatch.fnmatch(name, p) for p in patterns)

    # ---------- 从 LHS AST 提取信号名 ----------

    def _extract_name(self, node: Node) -> str | None:
        # 处理 Identifier / Pointer / Partselect
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, Pointer) and isinstance(node.var, Identifier):
            return node.var.name
        if isinstance(node, Partselect) and isinstance(node.var, Identifier):
            return node.var.name
        return None

    # ---------- 把 Pyverilog AST 转成 Expr ----------

    def _convert_expr(self, node: Node) -> Expr | None:
        # 这里只处理一部分运算：bit/partselect/xor/concat/add/sub/replicate
        if isinstance(node, Identifier):
            # 纯信号名（例如 mshr_used）
            return Expr("id", [node.name])

        if isinstance(node, IntConst):
            val = int(node.value, 0)
            return Expr("const", [val])

        if isinstance(node, Pointer):
            # var[bit]
            base = self._extract_name(node.var)
            if base is None:
                return None
            bit = int(node.ptr.value, 0)
            return Expr("bit", [base, bit])

        if isinstance(node, Partselect):
            base = self._extract_name(node.var)
            if base is None:
                return None
            hi = int(node.msb.value, 0)
            lo = int(node.lsb.value, 0)
            return Expr("slice", [base, hi, lo])

        if isinstance(node, BinaryOperator):
            opmap = {
                "+": "add",
                "-": "sub",
                "^": "xor",
                "|": "or",
                "&": "and"
            }
            op = opmap.get(node.__class__.__name__, None)
            # 注意：Pyverilog BinaryOperator 的 op 是 type 名称，如 'Plus','Minus','Xor'
            # 为了简单起见，这里用 node.__class__.__name__ 直接判断:
            tname = node.__class__.__name__.lower()
            if "plus" in tname:
                op = "add"
            elif "minus" in tname:
                op = "sub"
            elif "xor" in tname:
                op = "xor"
            elif "or" in tname:
                op = "or"
            elif "and" in tname:
                op = "and"

            if op is None:
                return None
            lhs = self._convert_expr(node.left)
            rhs = self._convert_expr(node.right)
            if lhs is None or rhs is None:
                return None
            return Expr(op, [lhs, rhs])

        if isinstance(node, UnaryOperator):
            # 例如 ~a
            tname = node.__class__.__name__.lower()
            if "ulnot" in tname or "unot" in tname:
                sub = self._convert_expr(node.right)
                if sub is None:
                    return None
                return Expr("not", [sub])
            # 其他类型先忽略
            return None

        if isinstance(node, Cond):
            # (cond ? true_expr : false_expr) → 暂视为非线性，直接放弃
            return None

        # 其他复杂类型暂不支持
        return None

