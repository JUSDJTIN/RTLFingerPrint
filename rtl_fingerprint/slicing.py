# rtl_fingerprint/slicing.py
from .ir import RTLIR, SignalIR, Expr

class ConeSlicer:
    def __init__(self, ir: RTLIR):
        self.ir = ir

    def slice_for_signal(self, sig: SignalIR) -> Expr:
        """
        TODO（真实实现）:
          - backward_slice 到顶层输入/关键寄存器
          - 常量传播 / DCE 等
        当前版本：直接返回 signal.expr
        """
        return self.ir.get_expr(sig)

    def backward_slice(design_graph, target_sig, stop_at_regs=True):
        worklist = [target_sig]
        visited = set()
        slice_nodes = set()

        while worklist:
            n = worklist.pop()
            if n in visited:
                continue
            visited.add(n)
            slice_nodes.add(n)

            for pred in design_graph.predecessors(n):
                # 如果 pred 是寄存器 / 输入 / clock/reset 等，就停
                if stop_at_regs and pred.kind in ("reg", "input", "clock", "reset"):
                    continue
                worklist.append(pred)
        return slice_nodes


