from __future__ import annotations

from psc.diagnostics import Diagnostic, DiagnosticEngine, SourceSpan


def _span(line: int = 1, col: int = 1, end_line: int = 1, end_col: int = 4) -> SourceSpan:
    return SourceSpan(
        file_id=7,
        ps_filename="Domain/Order.ps",
        start_line=line,
        start_col=col,
        end_line=end_line,
        end_col=end_col,
    )


def test_source_span_merge_and_location_formatting() -> None:
    left = _span(2, 3, 2, 8)
    right = _span(5, 1, 5, 9)

    merged = left.merge(right)

    assert merged.file_id == 7
    assert merged.ps_filename == "Domain/Order.ps"
    assert (merged.start_line, merged.start_col) == (2, 3)
    assert (merged.end_line, merged.end_col) == (5, 9)
    assert left.format_location() == "Domain/Order.ps:2:3"


def test_diagnostic_str_contains_severity_code_location_and_message() -> None:
    diagnostic = Diagnostic(
        code="PS000",
        severity="ERROR",
        message="Expected ';'",
        span=_span(4, 2),
    )

    assert str(diagnostic) == "ERROR [PS000] at Domain/Order.ps:4:2: Expected ';'"


def test_diagnostic_engine_reports_all_supported_codes() -> None:
    engine = DiagnosticEngine()
    span = _span()

    engine.report_syntax_error(span, "Expected expression")
    engine.report_ps001_access_violation(span, "Total", "private", "Order")
    engine.report_ps002_ambiguous_overload(span, "Put", "Put(int)", "Put(long)", "int")
    engine.report_ps003_circular_static_init(span, "A -> B -> A")
    engine.report_ps004_native_compile_dynamic(span, "NativeOrder")

    assert engine.has_errors() is True
    formatted = engine.format_all()
    assert "ERROR [PS000] at Domain/Order.ps:1:1: Expected expression" in formatted
    assert "'Order.Total' is 'private'" in formatted
    assert "'Put(int)' and 'Put(long)'" in formatted
    assert "A -> B -> A" in formatted
    assert "Type 'NativeOrder' is marked [NativeCompile] and cannot use 'dynamic'." in formatted


def test_empty_diagnostic_engine_has_no_errors_and_formats_to_empty_string() -> None:
    engine = DiagnosticEngine()

    assert engine.has_errors() is False
    assert engine.format_all() == ""


def test_diagnostic_formats_suggested_fix_hint_when_present() -> None:
    span = _span(10, 5)
    diag_with_hint = Diagnostic(
        code="PS001",
        severity="ERROR",
        message="Member 'Order.Price' is 'private' and cannot be accessed from this context.",
        span=span,
        hint="Expose 'Price' as public or provide a public getter.",
    )
    formatted = str(diag_with_hint)
    assert "ERROR [PS001] at Domain/Order.ps:10:5:" in formatted
    assert "(Hint: Expose 'Price' as public or provide a public getter.)" in formatted


def test_diagnostic_engine_default_hints_and_custom_hints() -> None:
    engine = DiagnosticEngine()
    span = _span(1, 1)

    engine.report_ps001_access_violation(span, "Secret", "private", "Vault")
    engine.report_ps002_ambiguous_overload(span, "Save", "Save(List<int>)", "Save(List<string>)", "list")
    engine.report_ps003_circular_static_init(span, "X -> Y -> X")
    engine.report_ps004_native_compile_dynamic(span, "FastMath")

    formatted = engine.format_all()
    assert "(Hint: Expose 'Secret' with 'public' or 'internal' visibility, or access it from within 'Vault'.)" in formatted
    assert "(Hint: Rename one overload, change parameter arity, or wrap the 'list' argument in a distinct record.)" in formatted
    assert "(Hint: Break the initialization cycle using a lazy property, method call, or local factory.)" in formatted
    assert "(Hint: Replace 'dynamic' with a concrete static type, interface, generic parameter, or 'object'.)" in formatted

    # Custom hint overrides default
    custom_engine = DiagnosticEngine()
    custom_engine.report_syntax_error(span, "Unexpected EOF", hint="Check for missing closing brace '}'.")
    assert "(Hint: Check for missing closing brace '}'.)" in custom_engine.format_all()
