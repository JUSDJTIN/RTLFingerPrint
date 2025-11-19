from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("uhdm")

from rtl_fingerprint.rmmg.builder import build_rmmg_from_design
from rtl_fingerprint.uhdm_compat import get_uhdm

uhdm, _ = get_uhdm()

DATA_DIR = Path(__file__).resolve().parent / "data"
WIDTH_DEMO = DATA_DIR / "width_demo.sv"


def _build_width_demo_graph(tmp_path: Path):
    surelog = shutil.which("surelog")
    if surelog is None:
        pytest.skip("Surelog binary is not available in PATH")

    workdir = tmp_path / "width_demo"
    workdir.mkdir()
    cmd = [
        surelog,
        "-top",
        "width_demo",
        "-parse",
        "-elabuhdm",
        "-d",
        "uhdm",
        str(WIDTH_DEMO),
    ]
    subprocess.run(cmd, cwd=workdir, check=True, capture_output=True, text=True)

    uhdm_db = workdir / "slpp_all" / "surelog.uhdm"
    assert uhdm_db.exists(), "Surelog did not produce surelog.uhdm"

    serializer = uhdm.Serializer()
    designs = serializer.Restore(str(uhdm_db))
    assert designs, "Serializer.Restore() returned no designs"
    graph = build_rmmg_from_design(designs[0])
    return graph


def _collect_widths(graph, signal_name: str):
    matches = []
    for node in graph.nodes.values():
        if node.attrs.get("signal_name") == signal_name:
            matches.append((node.kind, node.width))
    return matches


def test_basic_signal_widths(tmp_path):
    graph = _build_width_demo_graph(tmp_path)

    data_in = dict(_collect_widths(graph, "data_in"))
    assert data_in.get("input") == 8

    wide_bus = dict(_collect_widths(graph, "wide_bus"))
    assert wide_bus.get("output") == 16

    nibble = dict(_collect_widths(graph, "nibble"))
    assert nibble.get("logic") == 4

    narrow = dict(_collect_widths(graph, "narrow"))
    assert narrow.get("logic") == 3

    flag = dict(_collect_widths(graph, "flag"))
    assert flag.get("output") == 1

    line_mem = dict(_collect_widths(graph, "line_mem"))
    assert line_mem.get("memory") == 8
