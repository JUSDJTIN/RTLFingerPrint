# rtl_fingerprint/frontend/toy_frontend.py
from .base import FrontendBase
from ..ir import RTLIR, SignalIR, Expr


class ToyFrontend(FrontendBase):
    """
    Toy 前端：不真正解析 RTL，只构造一个玩具 IR，用于调通全流程。
      dcache_set_idx   = va[11:6] ^ {6{va[7]}}
      dcache_mshr_full = (mshr_used == 4)
    """

    def parse(self) -> RTLIR:
        # set_idx = slice(va, 11, 6) XOR replicate(bit(va,7), 6)
        d_idx_expr = Expr("xor", [
            Expr("slice", ["va", 11, 6]),
            Expr("replicate", [Expr("bit", ["va", 7]), 6])
        ])
        # mshr_full = (mshr_used == 4)
        mshr_full_expr = Expr("eq", ["mshr_used", 4])

        sigs = [
            SignalIR(
                name="dcache_set_idx",
                expr=d_idx_expr,
                module_path="DigitalTop.tile_prci_domain.boom_tile.dcache",
            ),
            SignalIR(
                name="dcache_mshr_full",
                expr=mshr_full_expr,
                module_path="DigitalTop.tile_prci_domain.boom_tile.dcache.mshrs",
            ),
        ]
        return RTLIR(signals=sigs)

