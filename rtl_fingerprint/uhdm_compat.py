"""Utilities for importing UHDM bindings across packaging variations."""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Callable, Iterator, Tuple

UhdmModules = Tuple[object, object]


def _build_iterate_gen(uhdm_mod: object) -> Callable[[int, object], Iterator[object]]:
    """Create a generator helper compatible with Surelog's util.vpi_iterate_gen."""

    def _iterator(tag: int, obj: object) -> Iterator[object]:
        it = getattr(uhdm_mod, "vpi_iterate")(tag, obj)
        if it is None:
            return
        while True:
            handle = getattr(uhdm_mod, "vpi_scan")(it)
            if handle is None:
                break
            yield handle

    return _iterator


def get_uhdm() -> UhdmModules:
    """Return `(uhdm, util)` regardless of how the bindings are packaged."""
    try:
        from uhdm import uhdm as uhdm_mod, util as util_mod  # type: ignore
        if hasattr(util_mod, "vpi_iterate_gen"):
            return uhdm_mod, util_mod
    except Exception:
        pass

    base_mod = importlib.import_module("uhdm")
    util_mod = SimpleNamespace(vpi_iterate_gen=_build_iterate_gen(base_mod))
    return base_mod, util_mod
