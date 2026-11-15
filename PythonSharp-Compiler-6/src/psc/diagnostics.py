from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Tracks exact 1-indexed line and column positions in the original .ps/.d.ps file."""

    file_id: int
    ps_filename: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def merge(self, other: SourceSpan) -> SourceSpan:
        return SourceSpan(
            file_id=self.file_id,
            ps_filename=self.ps_filename,
            start_line=self.start_line,
            start_col=self.start_col,
            end_line=other.end_line,
            end_col=other.end_col,
        )

    def format_location(self) -> str:
        return f"{self.ps_filename}:{self.start_line}:{self.start_col}"


@dataclass(slots=True)
class Diagnostic:
    code: str
    severity: Literal["ERROR", "WARNING"]
    message: str
    span: SourceSpan
    hint: str | None = None

    def __str__(self) -> str:
        base = f"{self.severity} [{self.code}] at {self.span.format_location()}: {self.message}"
        if self.hint:
            return f"{base} (Hint: {self.hint})"
        return base


@dataclass(slots=True)
class DiagnosticEngine:
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def report_syntax_error(self, span: SourceSpan, message: str, *, hint: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(code="PS000", severity="ERROR", message=message, span=span, hint=hint))

    def report_ps001_access_violation(
        self,
        span: SourceSpan,
        member_name: str,
        access_mod: str,
        owner_type: str,
        *,
        hint: str | None = None,
    ) -> None:
        default_hint = (
            f"Expose '{member_name}' with 'public' or 'internal' visibility, or access it from within '{owner_type}'."
        )
        self.diagnostics.append(
            Diagnostic(
                code="PS001",
                severity="ERROR",
                message=(
                    f"Member '{owner_type}.{member_name}' is '{access_mod}' and cannot be accessed from this context."
                ),
                span=span,
                hint=hint or default_hint,
            )
        )

    def report_ps002_ambiguous_overload(
        self,
        span: SourceSpan,
        method_name: str,
        sig_a: str,
        sig_b: str,
        erased_py_type: str,
        *,
        hint: str | None = None,
    ) -> None:
        default_hint = (
            f"Rename one overload, change parameter arity, or wrap the '{erased_py_type}' argument in a distinct record."
        )
        self.diagnostics.append(
            Diagnostic(
                code="PS002",
                severity="ERROR",
                message=(
                    f"Overloads '{sig_a}' and '{sig_b}' on '{method_name}' erase to "
                    f"identical Python runtime type '{erased_py_type}' at the same arity."
                ),
                span=span,
                hint=hint or default_hint,
            )
        )

    def report_ps003_circular_static_init(
        self, span: SourceSpan, cycle_path: str, *, hint: str | None = None
    ) -> None:
        default_hint = "Break the initialization cycle using a lazy property, method call, or local factory."
        self.diagnostics.append(
            Diagnostic(
                code="PS003",
                severity="ERROR",
                message=f"Circular static initializer cycle detected: {cycle_path}",
                span=span,
                hint=hint or default_hint,
            )
        )

    def report_ps004_native_compile_dynamic(
        self, span: SourceSpan, type_name: str, *, hint: str | None = None
    ) -> None:
        default_hint = "Replace 'dynamic' with a concrete static type, interface, generic parameter, or 'object'."
        self.diagnostics.append(
            Diagnostic(
                code="PS004",
                severity="ERROR",
                message=(f"Type '{type_name}' is marked [NativeCompile] and cannot use 'dynamic'."),
                span=span,
                hint=hint or default_hint,
            )
        )

    def report_ps005_surface_migration(
        self,
        span: SourceSpan,
        symbol_name: str,
        current_surface: int,
        target_surface: int,
        canonical_target: str | None = None,
        *,
        hint: str | None = None,
    ) -> None:
        default_hint = (
            f"Migrate to '{canonical_target}' to comply with targeted enterprise Surface {target_surface}."
            if canonical_target
            else f"Upgrade to a Surface {target_surface} enterprise API."
        )
        self.diagnostics.append(
            Diagnostic(
                code="PS005",
                severity="WARNING",
                message=(
                    f"Symbol '{symbol_name}' is a Surface {current_surface} API; "
                    f"project targets Surface {target_surface}."
                ),
                span=span,
                hint=hint or default_hint,
            )
        )

    def has_errors(self) -> bool:
        return any(d.severity == "ERROR" for d in self.diagnostics)

    def format_all(self) -> str:
        return "\n".join(str(d) for d in self.diagnostics)
