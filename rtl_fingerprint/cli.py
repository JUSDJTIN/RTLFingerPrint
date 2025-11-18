# rtl_fingerprint/cli.py
import argparse
from .compiler import FingerprintCompiler

def main():
    parser = argparse.ArgumentParser(description="RTL Fingerprint Compiler")
    parser.add_argument("-c", "--config", required=True, help="YAML config file")
    parser.add_argument("-o", "--out-prefix", default="out", help="Output prefix")
    args = parser.parse_args()

    compiler = FingerprintCompiler.from_file(args.config)
    compiler.run(out_prefix=args.out_prefix)

if __name__ == "__main__":
    main()

