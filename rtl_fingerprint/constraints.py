# rtl_fingerprint/constraints.py
from typing import List, Dict, Any
import json
import yaml
import csv
from .compiler_types import Fingerprint, Witness


class ConstraintSynthesizer:
    """
    根据指纹生成：
      - SMT 约束骨架 (constraints.smt2)
      - 参数域 (params.yml)
      - witness 样例 (witness.csv)
    """

    def __init__(self):
        self.smt_lines: List[str] = []
        self.params: Dict[str, Any] = {}
        self.witnesses: List[Witness] = []

    # ---------- 映射 ---------- #

    def _add_mapping(self, fp: Fingerprint):
        path = fp.path
        line_size = fp.attrs["line"]
        index_bits = fp.attrs.get("index_bits", [])
        xor_bits = fp.attrs.get("xor_bits", [])
        addr_base = fp.attrs.get("addr_base", "va")

        # 用 index_bits 推一个区间字符串，方便阅读（如 [11:6]）
        if index_bits:
            lo = min(index_bits)
            hi = max(index_bits)
            index_range_str = f"[{hi}:{lo}]"
        else:
            index_range_str = "[]"

        mask_val = line_size - 1

        self.smt_lines += [
            f"; Mapping constraints for {path}",
            f"; addr_base = {addr_base}, index_bits = {index_bits}, xor_bits = {xor_bits}",
            "(declare-fun A0 () (_ BitVec 64))",
            "(declare-fun A1 () (_ BitVec 64))",
            # 行对齐约束
            f"(assert (= (bvand A0 #x{mask_val:016x}) #x0))",
            f"(assert (= (bvand A1 #x{mask_val:016x}) #x0))",
            # TODO: 真正实现 set_idx(A0) == set_idx(A1)，目前先留注释
            "; TODO: add set_idx(A0) == set_idx(A1) constraint using index_bits/xor_bits",
        ]

        # toy：给一组示例地址对，用于快速 PoC
        probe0 = 0x80000000
        probe1 = 0x80000080

        self.params.setdefault("mapping", {})
        self.params["mapping"][path] = {
            "line_size": line_size,
            "index_bits": index_bits,
            "index_range": index_range_str,
            "xor_bits": xor_bits,
            "addr_base": addr_base,
            "probes": [{"addr0": probe0, "addr1": probe1}],
        }
        self.witnesses.append(
            Witness("Mapping", path, {"addr0": probe0, "addr1": probe1})
        )

    # ---------- 队列 ---------- #

    def _add_queue(self, fp: Fingerprint):
        path = fp.path
        cap = fp.attrs["cap"]
        hwm = fp.attrs["hwm"]

        self.smt_lines += [
            f"; Queue constraints for {path}",
            f"; cap = {cap}, hwm = {hwm}",
        ]
        self.params.setdefault("queue", {})
        self.params["queue"][path] = {"cap": cap, "hwm": hwm}
        self.witnesses.append(
            Witness("Queue", path, {"cap": cap, "hwm": hwm})
        )

    # ---------- 顶层 ---------- #

    def synthesize(self, fps: List[Fingerprint]):
        for fp in fps:
            if fp.ftype == "Mapping":
                self._add_mapping(fp)
            elif fp.ftype == "Queue":
                self._add_queue(fp)
            # 预测/仲裁类型可以在这里继续扩展

    # ---------- 输出 ---------- #

    def dump_smt(self, path: str):
        with open(path, "w") as f:
            f.write("\n".join(self.smt_lines))

    def dump_params(self, path: str):
        with open(path, "w") as f:
            yaml.safe_dump(self.params, f, sort_keys=False)

    def dump_witnesses(self, path: str):
        if not self.witnesses:
            return
        fieldnames = ["fp_type", "path", "params"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for w in self.witnesses:
                writer.writerow({
                    "fp_type": w.fp_type,
                    "path": w.path,
                    "params": json.dumps(w.params),
                })

