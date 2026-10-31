from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend.parser import Parser
from psc.lsp.server import LanguageServer, path_to_uri
from psc.semantics import GlobalSymbolTable, analyze_compilation_units

SURFACE_STUB = """
namespace PythonSharp.Raw.Time;
extern using time;

[SurfaceLevel(1)]
[CanonicalApi("PythonSharp.Diagnostics.Stopwatch.GetTimestamp")]
public static class Time
{
    [SurfaceLevel(1)]
    [CanonicalApi("PythonSharp.Diagnostics.Stopwatch.GetTimestamp")]
    [MapsTo("time")]
    public static extern double time();
}
"""

SURFACE_BRIDGE_STUB = """
namespace PythonSharp.Bridge.Time;
extern using time;

[SurfaceLevel(2)]
[CanonicalApi("PythonSharp.Diagnostics.Stopwatch.GetTimestamp")]
public static class Time
{
    [SurfaceLevel(2)]
    [CanonicalApi("PythonSharp.Diagnostics.Stopwatch.GetTimestamp")]
    [MapsTo("time")]
    public static extern double Time();
}
"""

ENTERPRISE_STUB = """
namespace PythonSharp.Diagnostics;
extern using time;

[SurfaceLevel(3)]
public static class Stopwatch
{
    [SurfaceLevel(3)]
    [MapsTo("time.time")]
    public static extern double GetTimestamp();
}
"""


def test_surface_migration_diagnostic_emits_ps005() -> None:
    diag = DiagnosticEngine()
    stub1 = Parser.from_source(SURFACE_STUB, file_id=-1, ps_filename="RawTime.d.ps", diagnostics=diag).parse_compilation_unit()
    stub2 = Parser.from_source(SURFACE_BRIDGE_STUB, file_id=-2, ps_filename="BridgeTime.d.ps", diagnostics=diag).parse_compilation_unit()
    stub3 = Parser.from_source(ENTERPRISE_STUB, file_id=-3, ps_filename="EnterpriseTime.d.ps", diagnostics=diag).parse_compilation_unit()

    user_code = """
namespace TestApp;

using PythonSharp.Bridge.Time;

public class Program
{
    public static void Main()
    {
        double t = Time.Time();
    }
}
"""
    user_unit = Parser.from_source(user_code, file_id=1, ps_filename="Program.ps", diagnostics=diag).parse_compilation_unit()
    units = [stub1, stub2, stub3, user_unit]
    symtab = GlobalSymbolTable(default_assembly_name="TestApp")

    # Target surface 3: should emit PS005 warnings for using Bridge namespace and calling Time.Time()
    analyze_compilation_units(units, symtab=symtab, diagnostics=diag, assembly_name="TestApp", target_surface=3)

    ps005_warnings = [d for d in diag.diagnostics if d.code == "PS005"]
    assert len(ps005_warnings) >= 1
    messages = " ".join(d.message for d in ps005_warnings)
    assert "Surface 2" in messages
    assert "targets Surface 3" in messages


def test_surface_migration_clean_on_enterprise() -> None:
    diag = DiagnosticEngine()
    stub3 = Parser.from_source(ENTERPRISE_STUB, file_id=-3, ps_filename="EnterpriseTime.d.ps", diagnostics=diag).parse_compilation_unit()

    clean_user_code = """
namespace TestApp;

using PythonSharp.Diagnostics;

public class Program
{
    public static void Main()
    {
        double t = Stopwatch.GetTimestamp();
    }
}
"""
    clean_unit = Parser.from_source(clean_user_code, file_id=1, ps_filename="Clean.ps", diagnostics=diag).parse_compilation_unit()
    units = [stub3, clean_unit]
    symtab = GlobalSymbolTable(default_assembly_name="TestApp")

    analyze_compilation_units(units, symtab=symtab, diagnostics=diag, assembly_name="TestApp", target_surface=3)

    ps005_warnings = [d for d in diag.diagnostics if d.code == "PS005"]
    assert len(ps005_warnings) == 0


def test_lsp_hover_displays_surface_ladder(tmp_path) -> None:
    server = LanguageServer()
    doc_path = tmp_path / "App.ps"
    doc_uri = path_to_uri(str(doc_path))

    custom_stub = """
namespace Custom.Raw.Metrics;
extern using metrics;

[SurfaceLevel(1)]
[CanonicalApi("Custom.Metrics.Monitor.GetRate")]
public static class RawMetrics
{
    [SurfaceLevel(1)]
    [CanonicalApi("Custom.Metrics.Monitor.GetRate")]
    [MapsTo("get_rate")]
    public static extern double get_rate();
}
"""

    doc_text = """namespace Demo;

public class Program
{
    public static void Main()
    {
        double t = RawMetrics.get_rate();
    }
}
"""
    server.documents[doc_uri] = server.analyze_document(doc_uri, doc_text)

    state = server.documents[doc_uri]
    assert state.symtab is not None

    diag = DiagnosticEngine()
    stub = Parser.from_source(custom_stub, file_id=-100, ps_filename="RawMetrics.d.ps", diagnostics=diag).parse_compilation_unit()
    analyze_compilation_units([stub], symtab=state.symtab, diagnostics=diag, assembly_name="Test")

    # Hover on `RawMetrics` (type)
    hover_type = server._compute_hover(doc_uri, line=7, col=22)
    assert hover_type is not None
    assert "Surface Tier:" in hover_type
    assert "Surface 1 (Raw ABI — Python-native snake_case)" in hover_type
    assert "Canonical Target:" in hover_type
    assert "Custom.Metrics.Monitor.GetRate" in hover_type

    # Hover on `get_rate` (member)
    hover_member = server._compute_hover(doc_uri, line=7, col=33)
    assert hover_member is not None
    assert "Surface Tier:" in hover_member
    assert "Surface 1 (Raw ABI — Python-native snake_case)" in hover_member
    assert "Canonical Target:" in hover_member
    assert "Custom.Metrics.Monitor.GetRate" in hover_member
