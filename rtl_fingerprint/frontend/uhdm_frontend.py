# rtl_fingerprint/frontend/uhdm_frontend.py
from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import subprocess
import fnmatch
from ..ir import RTLIR, SignalIR, Expr
from uhdm import uhdm, util

from dataclasses import dataclass, field
from typing import List

from ..rmmg.graph import RmmgGraph
from ..rmmg.builder import build_rmmg_from_design
from ..rmmg.annotator import annotate_basic_semantics
#from ..rmmg.annotator import annotate_basic_semantics
# from .base import FrontendBase  # 如果有基类就解开这行注释


class UHDMFrontend:  # 如果有 FrontendBase 就写 UHDMFrontend(FrontendBase)
    def __init__(self, cfg):
        """
        cfg: Config 对象，通常包含:
          - cfg.top_module   (例如 "BoomTile")
          - cfg.rtl_filelist (例如 "boom.filelist.f")
        """
        self.cfg = cfg
        self.serializer = uhdm.Serializer()
        self.design = None
        self.graph = None
        self.arch_visible_rules = list(cfg.arch_visible_rules) 
        self.workdir = Path(".").resolve()

    def parse(self) -> RTLIR:
        if self.design is None:
            self._run_surelog_and_load_uhdm()
        #design = self._run_surelog_and_load_uhdm()
        signals = self._extract_signals()
        return RTLIR(signals=signals)

    # ---------- 1) 调用 surelog 生成 surelog.uhdm + 反序列化 ----------
    def _run_surelog_and_load_uhdm(self):
        #workdir = Path(".").resolve()
        slpp_dir = self.workdir / "slpp_all"
        uhdm_bin = slpp_dir / "surelog.uhdm"

        cmd = [
            "surelog",
            "-top", self.cfg.top_module,
            "-f", self.cfg.rtl_filelist,
            "-elabuhdm",
            "-d", "uhdm",
            "-parse",
        ]
        print("[INFO] Running Surelog:", " ".join(cmd))
        ret = subprocess.run(cmd, cwd=self.workdir)
        if ret.returncode != 0:
            raise RuntimeError(
                f"Surelog failed: {ret.returncode}, see {slpp_dir}/surelog.log"
            )

        if not uhdm_bin.exists():
            raise FileNotFoundError(f"UHDM database not found: {uhdm_bin}")

        #s = uhdm.Serializer()
        designs = self.serializer.Restore(str(uhdm_bin))
        if not designs:
            raise RuntimeError("Serializer.Restore() returned empty design list")
        self.design = designs[0]
        module_iterator = uhdm.vpi_iterate(uhdm.uhdmallModules,self.design)
        #while(True):
        #    vpiObj_module = uhdm.vpi_scan(module_iterator)
        #    if vpiObj_module is None:
        #        break
        #    print("vpiname:",uhdm.vpi_get_str(uhdm.vpiName,vpiObj_module))
        #    print("Defname:",uhdm.vpi_get_str(uhdm.vpiDefName,vpiObj_module))
        #    print("Fullname:",uhdm.vpi_get_str(uhdm.vpiFullName,vpiObj_module))
        print("[INFO] UHDM design restored")
        #return design

    def build_rmmg(self) -> RmmgGraph:
        if self.design is None:
            self._run_surelog_and_load_uhdm()
            self.graph = build_rmmg_from_design(self.design,self.arch_visible_rules)
            annotate_basic_semantics(self.graph,self.arch_visible_rules)
        else:
            self.graph = build_rmmg_from_design(self.design,self.arch_visible_rules)
            annotate_basic_semantics(self.graph,self.arch_visible_rules)
        print("[RMMG] ", self.graph.summary())

    def save_rmmg(self):
        outdir = self.workdir/"RmmgGraph.txt"
        with outdir.open("w+") as f:
            for node in self.graph.nodes.values():
                f.write(
                    f"NODE {node.id} {node.hier_name} "
                    f"kind={node.kind} width={node.width} "
                    f"arch_visible={node.attrs.get('is_arch_visible', False)}\n"
                        )
            for edge in self.graph.edges:
                f.write(
                    f"EDGE {edge.src}->{edge.dst} seq={edge.is_seq} "
                    f"cond={edge.cond}\n"
                        )
        print(f"[RMMG]: graph summary write to {outdir}")

    # ---------- 2) 在 UHDM 里找到我们关心的信号 ----------
    def _extract_signals(self) -> List[SignalIR]:
        signals: List[SignalIR] = []

        # 先用简单的名字匹配，后面可以改成配置驱动
        target_patterns = ["*set_idx*", "*mshr_full*"]

        for mod in util.vpi_iterate_gen(uhdm.uhdmallModules, self.design):
            mod_name = uhdm.vpi_get_str(uhdm.vpiFullName, mod)
            # 遍历模块里的所有连续赋值 vpiContAssign
            for ca in util.vpi_iterate_gen(uhdm.vpiContAssign, mod):
                lhs = uhdm.vpi_handle(uhdm.vpiLhs, ca)
                rhs = uhdm.vpi_handle(uhdm.vpiRhs, ca)

                lhs_name = self._lhs_name(lhs)
                if lhs_name is None:
                    continue

                if not self._match_any(lhs_name, target_patterns):
                    continue

                expr = self._to_expr(rhs)
                if expr is None:
                    continue

                signals.append(
                    SignalIR(
                        name=lhs_name,
                        expr=expr,
                        module_path=mod_name,
                    )
                )

        print(f"[INFO] UHDMFrontend: extracted {len(signals)} candidate signals")
        return signals

    def _match_any(self, name: str, patterns: List[str]) -> bool:
        return any(fnmatch.fnmatch(name, p) for p in patterns)

    # ---------- 3) 把 LHS 和 RHS 的 UHDM/VPI 节点转成你的 Expr ----------
    def _lhs_name(self, obj) -> Optional[str]:
        # 通用：vpiName
        name = uhdm.vpi_get_str(uhdm.vpiName, obj)
        return name or None

    def _to_expr(self, obj) -> Optional[Expr]:
        """
        UHDM VPI 对象 -> Expr
        """
        if obj is None:
            return None

        t = uhdm.vpi_get(uhdm.vpiType, obj)

        # 常量
        if t == uhdm.vpiConstant:
            v = uhdm.vpi_get_str(uhdm.vpiValue, obj)
            try:
                val = int(v, 0)
            except ValueError:
                return None
            return Expr("const", [val])

        # 变量引用（net/reg/logic/param/ref）
        if t in (
            uhdm.vpiNet,
            uhdm.vpiReg,
            uhdm.vpiLogicVar,
            uhdm.vpiIntegerVar,
            uhdm.vpiParameter,
            uhdm.vpiRefObj,
        ):
            name = uhdm.vpi_get_str(uhdm.vpiName, obj)
            return Expr("id", [name])

        # 位选
        if t == uhdm.vpiBitSel:
            var = uhdm.vpi_handle(uhdm.vpiVarSelect, obj)
            idx = uhdm.vpi_handle(uhdm.vpiIndex, obj)
            base = self._to_expr(var)
            idx_e = self._to_expr(idx)
            if base is None or idx_e is None or idx_e.op != "const":
                return None
            return Expr("bit", [base, idx_e.args[0]])

        # 片选
        if t == uhdm.vpiPartSelect:
            var = uhdm.vpi_handle(uhdm.vpiVarSelect, obj)
            left = uhdm.vpi_handle(uhdm.vpiLeftRange, obj)
            right = uhdm.vpi_handle(uhdm.vpiRightRange, obj)
            base = self._to_expr(var)
            hi = self._to_expr(left)
            lo = self._to_expr(right)
            if base is None or hi is None or lo is None:
                return None
            if hi.op != "const" or lo.op != "const":
                return None
            return Expr("slice", [base, hi.args[0], lo.args[0]])

        # 运算
        if t == uhdm.vpiOperation:
            optype = uhdm.vpi_get(uhdm.vpiOpType, obj)
            op_name = self._map_op(optype)
            ops = []
            it = uhdm.vpi_iterate(uhdm.vpiOperand, obj)
            while True:
                o = uhdm.vpi_scan(it)
                if o is None:
                    break
                sub = self._to_expr(o)
                if sub is None:
                    return None
                ops.append(sub)
            return Expr(op_name, ops)

        # 其他暂时不处理
        return None

    def _map_op(self, optype: int) -> str:
        """
        映射 vpiOpType -> Expr.op 字符串。
        这里只列几个常见的，后面你可以根据需要补全。
        """
        mapping = {
            uhdm.vpiAddOp: "add",
            uhdm.vpiSubOp: "sub",
            uhdm.vpiMultOp: "mul",
            uhdm.vpiEqOp: "eq",
            uhdm.vpiNeqOp: "neq",
            uhdm.vpiLtOp: "lt",
            uhdm.vpiLeOp: "le",
            uhdm.vpiGtOp: "gt",
            uhdm.vpiGeOp: "ge",
            uhdm.vpiBitAndOp: "band",
            uhdm.vpiBitOrOp: "bor",
            uhdm.vpiBitXorOp: "bxor",
            uhdm.vpiUnaryNegOp: "neg",
        }
        return mapping.get(optype, f"op_{optype}")

