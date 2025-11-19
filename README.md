# RTLFingerPrint

RTLFingerPrint is an RTL fingerprint compiler that parses Verilog/SystemVerilog
through either a toy frontend or a UHDM/Surelog pipeline, extracts
microarchitectural fingerprints, and emits constraints/ablation configs.

## Environment Setup

All tooling requirements (Surelog, UHDM bindings, and Python packages) are
documented in [docs/ENV_SETUP.md](docs/ENV_SETUP.md).  The short version:

```bash
./scripts/setup_env.sh
source .venv/bin/activate
python -m rtl_fingerprint.cli -c rtl_fingerprint/config_toy.yml -o demo
```

### Dumping the demo RMMG graph

To verify the UHDM frontend end-to-end (Surelog parsing → RMMG build →
serialization), run the compiler against the self-contained
`tests/data/width_demo.sv` fixture:

```bash
python -m rtl_fingerprint.cli -c rtl_fingerprint/config_width_demo.yml -o width_demo
```

The command writes the textual graph to `RmmgGraph.txt` (a copy of the latest run
is kept under [`docs/examples/width_demo_rmmg.txt`](docs/examples/width_demo_rmmg.txt)).
Each node line shows the resolved kind and `width=`, letting you double-check
interface widths directly in the generated RMMG; the most notable signal widths
are summarized in [`docs/examples/width_demo_summary.md`](docs/examples/width_demo_summary.md).

The setup script installs the Python dependencies listed in
[`requirements.txt`](requirements.txt) and verifies that Surelog + the UHDM
bindings are available.  If you already ran Surelog elsewhere and have a
`slpp_dir/surelog.uhdm` tree, point `rtl.uhdm_database` in your config at that
file to reuse it instead of re-running Surelog.
