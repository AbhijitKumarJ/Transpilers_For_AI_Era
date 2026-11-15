# Generate stubs for the entire pytorch or transformers library
# stubgen -p torch -o ./your_transpiler_cache/stubs/
# stubgen -p transformers -o ./your_transpiler_cache/stubs/
# pyright --createstub torch
# pyright --createstub transformers
# pyright --createstub sklearn

# stubgen -p sklearn -o ./transpiler_stubs/
# stubgen -p transformers -o ./transpiler_stubs/
pyright --createstub os
pyright --createstub matplotlib




$ pyright --createstub matplotlib
Type stub was created for 'matplotlib'

$ psc bindgen -h
usage: psc bindgen [-h] [-o OUT_DIR] [--root-namespace ROOT_NAMESPACE] [--triple-surface] target

positional arguments:
  target                Path to .pyi file or directory of .pyi stubs

options:
  -h, --help            show this help message and exit
  -o, --out-dir OUT_DIR
                        Output directory (default: .ps-stubs/)
  --root-namespace ROOT_NAMESPACE
                        Root namespace prefix (default: Extern)
  --triple-surface      Generate 4-file Triple Surface bundle (primitives, raw surface 1, csharp bridge
                        surface 2, enterprise surface 3)

$ psc bindgen -o stdlib2/matplotlib/ --triple-surface typings/matplotlib