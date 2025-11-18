# rtl_fingerprint/compiler.py
from typing import List
from .config import Config, load_config
from .frontend import ToyFrontend, UHDMFrontend
from .targets import TargetSelector
from .slicing import ConeSlicer
from .patterns import PatternExtractor
from .constraints import ConstraintSynthesizer
from .ablation import AblationGenerator
from .compiler_types import Fingerprint
from .rmmg.query import RmmgQueryEngine

class FingerprintCompiler:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @classmethod
    def from_file(cls, config_path: str) -> "FingerprintCompiler":
        cfg = load_config(config_path)
        return cls(cfg)

    def run(self, out_prefix: str = "out"):
        # 1) 选择前端
        if self.cfg.frontend == "uhdm":
            fe = UHDMFrontend(self.cfg)
        else:
            fe = ToyFrontend(self.cfg)
        
        # 2) generate the rmmg
        fe.build_rmmg()

        #3) save the rmmg
        fe.save_rmmg()

        #3.1 test 
        engine = RmmgQueryEngine(fe.graph)

        #paths = engine.query_mshr_to_rob_commit(max_depth=60, max_paths=10)
        paths = engine.query_custom(
                source_pred=lambda n: n.hier_name == "work@MSHR.meta_tag",
                target_pred=lambda n: "work@MSHR.io_schedule_bits_b_bits_tag" in n.hier_name,
                max_depth=10,
                max_paths=5,
                )
        engine.pretty_print_paths(paths,max_paths=3)

        paths = engine.query_dcache_to_rob_data()
        engine.pretty_print_paths(paths,max_paths=3)

        self.debug_module_edges(fe.graph,"work@MSHR")
        self.debug_module_edges(fe.graph,"work@BoomMSHRFile")
        self.debug_module_edges(fe.graph,"work@Rob")
        self.debug_module_edges(fe.graph,"work@BoomCore")
        
        return 

        # 3) 目标选择
        ts = TargetSelector(ir, self.cfg.analysis)
        targets = ts.select_targets()

        # 4) 小锥切片 + 模式识别
        slicer = ConeSlicer(ir)
        extractor = PatternExtractor()
        fingerprints: List[Fingerprint] = []

        for mech, sigs in targets.items():
            for sig in sigs:
                expr = slicer.slice_for_signal(sig)
                fp = extractor.extract_for_mech(mech, sig, expr)
                if fp is not None:
                    fingerprints.append(fp)

        # 5) 约束 & witness
        cs = ConstraintSynthesizer()
        cs.synthesize(fingerprints)

        # 6) 消融配置
        ab = AblationGenerator()
        ab.add_default(fingerprints)

        # 7) 输出
        self._dump_fingerprints(fingerprints, out_prefix + ".fingerprints.json")
        cs.dump_smt(out_prefix + ".constraints.smt2")
        cs.dump_params(out_prefix + ".params.yml")
        cs.dump_witnesses(out_prefix + ".witness.csv")
        ab.dump(out_prefix + ".ablation.cfg")

        print(f"[INFO] Fingerprints generated: {len(fingerprints)}")

    def debug_module_edges(self,graph, module_name_substr: str):
        module_nodes = [
            (nid, n) for nid, n in graph.nodes.items()
            if module_name_substr in n.hier_name
        ]
        in_cnt = out_cnt = 0
        node_ids = {nid for nid, _ in module_nodes}
    
        for e in graph.edges:
            if e.src in node_ids:
                out_cnt += 1
            if e.dst in node_ids:
                in_cnt += 1
    
        print(f"[DEBUG] module '{module_name_substr}': "
              f"nodes={len(module_nodes)}, in_edges={in_cnt}, out_edges={out_cnt}")


    @staticmethod
    def _dump_fingerprints(fps: List[Fingerprint], path: str):
        import json
        data = {"fingerprints": []}
        for fp in fps:
            data["fingerprints"].append({
                "type": fp.ftype,
                "path": fp.path,
                "conf": fp.conf,
                "impact": fp.impact,
                "attrs": fp.attrs,
            })
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


