# Width Demo RMMG Snapshot

The sample design in `tests/data/width_demo.sv` can be compiled through the UHDM frontend using:

```
python -m rtl_fingerprint.cli -c rtl_fingerprint/config_width_demo.yml -o width_demo
```

This command regenerates the textual dump stored in `docs/examples/width_demo_rmmg.txt`. The key interface widths encoded in that graph are:

| Signal | Kind  | Width (bits) |
| ------ | ----- | ------------- |
| `data_in` | input  | 8 |
| `wide_bus` | output | 16 |
| `nibble` | internal logic | 4 |
| `narrow` | internal logic | 3 |
| `line_mem` | memory | 8 |

Refer to the dump for the complete node/edge inventory when auditing the generated RMMG.
