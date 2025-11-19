# RTLFingerPrint Environment Setup

This document describes everything that is required to run the RTL fingerprint
compiler locally.  The project depends on two classes of tools:

1.  **System tools** that translate SystemVerilog to UHDM (Surelog + UHDM
    Python bindings).
2.  **Python packages** that power the CLI, toy frontend and Chipyard demo.

> **Note:** The commands in this guide were validated in the provided execution
> environment.  If a proxy blocks `git clone`, you can still fetch the required
> sources from GitHub's `codeload` endpoint as demonstrated below.

## 1. System Dependencies

Install a recent C++ toolchain and libraries that Surelog requires.  On Ubuntu
22.04 the following packages are sufficient:

```bash
sudo apt-get update
sudo apt-get install -y \
    build-essential cmake python3 python3-venv \
    bison flex libfl-dev libgmp-dev

# Python helpers required by the Surelog/UHDM build
python3 -m pip install --user orderedmultidict build
```

### Build Surelog with UHDM Python bindings

```
curl -L https://codeload.github.com/chipsalliance/Surelog/tar.gz/refs/tags/v1.86 \
  -o Surelog-v1.86.tar.gz
mkdir -p Surelog
tar -xf Surelog-v1.86.tar.gz --strip-components=1 -C Surelog
cd Surelog

# Populate the submodules without relying on git
curl -L https://codeload.github.com/chipsalliance/UHDM/tar.gz/refs/heads/master \
  -o third_party/UHDM.tar.gz
mkdir -p third_party/UHDM
tar -xf third_party/UHDM.tar.gz --strip-components=1 -C third_party/UHDM
curl -L https://codeload.github.com/antlr/antlr4/tar.gz/refs/heads/dev \
  -o third_party/antlr4.tar.gz
mkdir -p third_party/antlr4
tar -xf third_party/antlr4.tar.gz --strip-components=1 -C third_party/antlr4
curl -L https://codeload.github.com/nlohmann/json/tar.gz/refs/heads/develop \
  -o third_party/json.tar.gz
mkdir -p third_party/json
tar -xf third_party/json.tar.gz --strip-components=1 -C third_party/json
curl -L https://codeload.github.com/google/googletest/tar.gz/refs/heads/main \
  -o third_party/googletest.tar.gz
mkdir -p third_party/googletest
tar -xf third_party/googletest.tar.gz --strip-components=1 \
  -C third_party/googletest

# UHDM also vendors capnproto/googletest
curl -L https://codeload.github.com/capnproto/capnproto/tar.gz/refs/heads/master \
  -o third_party/UHDM/third_party/capnproto.tar.gz
mkdir -p third_party/UHDM/third_party/capnproto
tar -xf third_party/UHDM/third_party/capnproto.tar.gz --strip-components=1 \
  -C third_party/UHDM/third_party/capnproto
curl -L https://codeload.github.com/google/googletest/tar.gz/refs/heads/main \
  -o third_party/UHDM/third_party/googletest.tar.gz
mkdir -p third_party/UHDM/third_party/googletest
tar -xf third_party/UHDM/third_party/googletest.tar.gz --strip-components=1 \
  -C third_party/UHDM/third_party/googletest

mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release \
      -DSURELOG_WITH_PYTHON=ON \
      -DUHDM_USE_HOST_INSTALL=OFF \
      ..
cmake --build . -j$(nproc)
cmake --install . --prefix "$HOME/.local"
```

This produces:

- `~/.local/bin/surelog` – the binary consumed by `UHDMFrontend`.
- Python bindings (`uhdm` package) inside `lib/python*/site-packages` under the
  chosen prefix.

Update your shell so both artifacts are discoverable:

```bash
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$HOME/.local/lib/python3.X/site-packages:$PYTHONPATH"
```

Replace `3.X` with the Python version that was used while building Surelog.
You can place the exports in `~/.bashrc` to make them permanent.

## 2. Python Dependencies

Create (or reuse) a virtual environment and install the packages listed in
`requirements.txt`.  A helper script is provided:

```bash
./scripts/setup_env.sh
```

The script performs the following steps:

1. Creates `.venv` in the repository root if it does not exist.
2. Upgrades `pip` inside the environment.
3. Installs the dependencies declared in `requirements.txt` (PyYAML and
   Pyverilog for the toy/Chipyard frontends) and, if missing, fetches the
   prebuilt `uhdm` wheel from PyPI.
4. Verifies that the `surelog` binary can be located.
5. Verifies that the UHDM Python bindings are importable.
6. If `slpp_dir/surelog.uhdm` (or the path specified via
   `$UHDM_DB_UNDER_TEST`) exists, restores it via the UHDM bindings to ensure
   the environment can analyze an existing Surelog database.

If you see warnings about missing Surelog or UHDM bindings, ensure that the
previous section was followed.

## 3. Verifying the Setup

After the tooling is installed activate the virtual environment and run the toy
config included in the repo:

```bash
source .venv/bin/activate
python -m rtl_fingerprint.cli -c rtl_fingerprint/config_toy.yml -o demo
```

For the UHDM frontend, make sure a valid filelist and top module are configured
in your YAML config before invoking the CLI with `frontend: "uhdm"`.

### Testing an existing `slpp_dir/surelog.uhdm`

If you already ran Surelog elsewhere and copied the resulting
`slpp_dir/surelog.uhdm` directory into the repository, you can test the Python
bindings without re-running Surelog:

1. Ensure the UHDM file is available (for example under
   `<repo>/slpp_dir/surelog.uhdm`).  The setup script automatically attempts to
   restore this file (or whatever path you place in `$UHDM_DB_UNDER_TEST`).
2. In your RTL config, set `rtl.uhdm_database: "slpp_dir/surelog.uhdm"` so the
   CLI reuses the database instead of invoking Surelog again.
3. Run `python -m rtl_fingerprint.cli -c <your_config>.yml -o out` from the repo
   root.  The UHDM frontend will skip Surelog and deserialize the provided file
   directly.

This workflow is handy when you only have access to a large Surelog output and
want to confirm the rest of the toolchain can analyze it.

## 4. Troubleshooting

- **`pip install` fails with proxy/403 errors:** double-check that your
  workstation can reach `https://pypi.org`.  If you are behind a proxy, export
  `HTTPS_PROXY`/`HTTP_PROXY` before running the setup script.
- **`ModuleNotFoundError: uhdm`:** confirm that Surelog was built with
  `-DSURELOG_WITH_PYTHON=ON`, install the `uhdm` wheel via
  `python -m pip install uhdm`, and ensure the resulting site-packages
  directory is part of `PYTHONPATH`.
- **`surelog` command not found:** ensure `$HOME/.local/bin` (or the prefix you
  used while installing Surelog) is in `PATH`.

With the steps above, every dependency required by RTLFingerPrint is installed
and validated.
