from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

import pytest

from psc import ArtifactEmitter, compile_sources
from psc.cli import main as cli_main

STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def test_pyc_bytecode_line_pinning_reports_exact_ps_file_and_line(tmp_path: Path) -> None:
    """
    Verifies Milestone 6 (Pass 3B Bytecode Line-Pinning):
      1. Compiles `Services/PaymentGateway.ps` where line 14 throws `ValueError`.
      2. Loads the emitted PEP 552 `.pyc` bytecode from disk via `ArtifactEmitter.load_code_from_pyc`.
      3. Executes `charge(-50)` and captures the native CPython traceback.
      4. Asserts that CPython's native traceback prints:
         `File "Services/PaymentGateway.ps", line 14, in charge`
         with zero custom `sys.excepthook` or third-party traceback wrappers!
    """
    ps_source = "\n".join(
        [
            "/* Line 01 */ namespace Commerce.Payments;",
            "/* Line 02 */ ",
            "/* Line 03 */ public class ValueError : Exception",
            "/* Line 04 */ {",
            "/* Line 05 */     public ValueError(string msg) { }",
            "/* Line 06 */ }",
            "/* Line 07 */ ",
            "/* Line 08 */ public class PaymentGateway",
            "/* Line 09 */ {",
            "/* Line 10 */     public int Charge(int amount)",
            "/* Line 11 */     {",
            "/* Line 12 */         if (amount <= 0)",
            "/* Line 13 */         {",
            '/* Line 14 */             throw new ValueError("Amount must be positive");',
            "/* Line 15 */         }",
            "/* Line 16 */         return amount * 100;",
            "/* Line 17 */     }",
            "/* Line 18 */ }",
        ]
    )

    artifacts, diag = compile_sources(
        sources={"Services/PaymentGateway.ps": ps_source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
        emit_pyc=True,
    )
    assert not diag.has_errors(), diag.format_all()
    assert len(artifacts) == 1

    art = artifacts[0]
    assert art.py_path.exists()
    assert art.pyc_path is not None and art.pyc_path.exists()
    assert art.pycache_pyc_path is not None and art.pycache_pyc_path.exists()

    # Load the marshaled code object directly from the emitted `.pyc` file on disk
    loaded_code = ArtifactEmitter.load_code_from_pyc(art.pyc_path)
    assert loaded_code.co_filename == "Services/PaymentGateway.ps"

    ns_globals: dict[str, Any] = {}
    exec(loaded_code, ns_globals)
    value_error_type = ns_globals["ValueError"]
    assert issubclass(value_error_type, Exception)

    gateway = ns_globals["PaymentGateway"]()
    assert gateway.charge(25) == 2500

    with pytest.raises(value_error_type) as exc_info:
        gateway.charge(-10)

    tb_lines = traceback.format_exception(type(exc_info.value), exc_info.value, exc_info.value.__traceback__)
    tb_text = "".join(tb_lines)

    # CPython's native traceback reports the exact `.ps` file and line 14!
    assert 'File "Services/PaymentGateway.ps", line 14, in charge' in tb_text


def test_cli_check_and_build_multi_file_psproj(tmp_path: Path) -> None:
    """
    Verifies `psc check` and `psc build` via `cli_main` on a multi-file `.psproj`
    project with circular cross-file references (`Order.ps` <-> `OrderCache.ps`).
    """
    proj_dir = tmp_path / "commerce_sample"
    (proj_dir / "Domain").mkdir(parents=True)
    (proj_dir / "Services").mkdir(parents=True)

    (proj_dir / "Commerce.psproj").write_text(
        """
        <Project Sdk="PythonSharp.Sdk">
          <PropertyGroup>
            <AssemblyName>Commerce.Sample</AssemblyName>
            <OutputPath>dist</OutputPath>
            <TargetPython>3.11</TargetPython>
            <EmitPyc>true</EmitPyc>
          </PropertyGroup>
        </Project>
        """.strip(),
        encoding="utf-8",
    )

    (proj_dir / "Domain" / "Order.ps").write_text(
        """
        namespace Commerce.Domain;

        using Commerce.Services;

        public record Order(int Id, decimal Total, bool IsActive);
        """.strip(),
        encoding="utf-8",
    )

    (proj_dir / "Services" / "OrderCache.ps").write_text(
        """
        namespace Commerce.Services;

        using PythonSharp.Core;
        using Commerce.Domain;

        public class OrderCache : IDisposable
        {
            private readonly Dict<int, Order> _store = new Dict<int, Order>();

            public void Put(Order order) => _store[order.Id] = order;
            public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);

            public List<int> GetActiveIds()
            {
                return _store.Values()
                    .Where(o => o.IsActive)
                    .Select(o => o.Id)
                    .ToList();
            }

            public void Dispose() => _store.Clear();
        }
        """.strip(),
        encoding="utf-8",
    )

    psproj_file = proj_dir / "Commerce.psproj"

    # 1. Run `psc check`
    rc_check = cli_main(["check", str(psproj_file)])
    assert rc_check == 0

    # 2. Run `psc build`
    rc_build = cli_main(["build", str(psproj_file)])
    assert rc_build == 0

    dist_dir = proj_dir / "dist"
    assert (dist_dir / "commerce" / "__init__.py").exists()
    assert (dist_dir / "commerce" / "domain.py").exists()
    assert (dist_dir / "commerce" / "domain.pyc").exists()
    assert (dist_dir / "commerce" / "services.py").exists()
    assert (dist_dir / "commerce" / "services.pyc").exists()
