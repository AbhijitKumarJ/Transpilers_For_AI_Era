use rsharpc::diagnostics::DiagnosticEngine;
use rsharpc::frontend::{
    AccessMod, BorrowMode, EffectSignature, ExprKind, Lexer, MemberDecl, Parser, PrimitiveLowering,
    Stmt, TypeKind,
};

fn parse_source(
    filename: &str,
    src: &str,
) -> (rsharpc::frontend::CompilationUnit, DiagnosticEngine) {
    let mut diag = DiagnosticEngine::new();
    let tokens = {
        let mut lexer = Lexer::new(src, 0, filename, &mut diag);
        lexer.tokenize()
    };
    let unit = {
        let mut parser = Parser::new(tokens, 0, filename, &mut diag);
        parser.parse_compilation_unit()
    };
    (unit, diag)
}

#[test]
fn test_parses_archetypes_throws_and_decimal_literals() {
    let source = r#"
namespace Commerce.Checkout;

using Commerce.Domain;
extern using rust_decimal::Decimal as Decimal;

public record Order(int Id, decimal Total);
public record ValidationError(string Reason);

public service class OrderHandler
{
    private readonly TaxCalculator _tax;

    public OrderHandler(TaxCalculator tax) => _tax = tax;

    public void Checkout(Order order, string coupon) throws ValidationError
    {
        if (order.Total <= 0.0m)
            throw new ValidationError("Order total must be positive");

        ApplyCoupon(order, coupon);
        _tax.RecordAudit(order);
    }

    private void ApplyCoupon(Order order, string code)
    {
        if (code == "SAVE10")
            order.Total -= 10.0m;
    }
}
"#;

    let (unit, diag) = parse_source("OrderHandler.rsharp", source);
    assert!(
        !diag.has_errors(),
        "Unexpected syntax errors: {}",
        diag.format_all()
    );
    assert_eq!(unit.namespace, vec!["Commerce", "Checkout"]);
    assert_eq!(unit.imports.len(), 2);
    assert!(unit.imports[1].is_extern_crate);
    assert_eq!(unit.imports[1].path, vec!["rust_decimal", "Decimal"]);
    assert_eq!(unit.imports[1].alias.as_deref(), Some("Decimal"));

    assert_eq!(unit.types.len(), 3);
    assert_eq!(unit.types[0].name, "Order");
    assert_eq!(unit.types[0].kind, TypeKind::Record { is_struct: false });
    assert_eq!(unit.types[0].primary_ctor_params.len(), 2);

    let service = &unit.types[2];
    assert_eq!(service.name, "OrderHandler");
    assert_eq!(service.kind, TypeKind::ServiceClass);
    assert_eq!(service.access, AccessMod::Public);

    let checkout_method = service
        .members
        .iter()
        .find_map(|m| match m {
            MemberDecl::Method(md) if md.name == "Checkout" => Some(md),
            _ => None,
        })
        .expect("Expected Checkout method");

    assert_eq!(
        checkout_method
            .explicit_throws
            .as_ref()
            .unwrap()
            .short_name(),
        "ValidationError"
    );
    assert!(matches!(
        checkout_method.inferred_effect,
        EffectSignature::Fallible { .. }
    ));
}

#[test]
fn test_parses_primitive_stdlib_declarations_and_borrow_attributes() {
    let stub_src = r#"
namespace RustSharp.Core;

[MapsTo("std::vec::Vec")]
[ParamType("&[{T}]")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("Vec::new()")]
    public extern List();

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Mutates]
    [MapsTo("push")]
    public extern void Add([Moves] T item);
}
"#;

    let (unit, diag) = parse_source("RustSharp.Core.d.rsharp", stub_src);
    assert!(
        !diag.has_errors(),
        "Unexpected syntax errors: {}",
        diag.format_all()
    );
    assert!(unit.is_ambient_stub);

    let list_decl = &unit.types[0];
    assert_eq!(list_decl.name, "List");
    assert_eq!(
        list_decl.kind,
        TypeKind::PrimitiveClass { is_struct: false }
    );
    assert_eq!(
        list_decl.primitive_rust_target.as_deref(),
        Some("std::vec::Vec")
    );
    assert_eq!(list_decl.primitive_param_type.as_deref(), Some("&[{T}]"));

    let add_method = list_decl
        .members
        .iter()
        .find_map(|m| match m {
            MemberDecl::Method(md) if md.name == "Add" => Some(md),
            _ => None,
        })
        .expect("Expected Add method");

    assert_eq!(add_method.inferred_self_borrow, BorrowMode::MutBorrow);
    assert_eq!(
        add_method.primitive_lowering,
        PrimitiveLowering::DirectSymbol {
            rust_path: "push".to_string()
        }
    );
    assert_eq!(add_method.params[0].inferred_borrow, BorrowMode::OwnedMove);
}

#[test]
fn test_parses_range_slicing_null_coalescing_and_switch_expressions() {
    let src = r#"
namespace Telemetry.Ingest;

public static class PacketParser
{
    public static int Inspect(ReadOnlySpan<byte> buffer, int? overrideLen)
    {
        ReadOnlySpan<byte> header = buffer[0..16];
        int effective = overrideLen ?? header.Length;
        return effective switch
        {
            0 => -1,
            16 => 1,
            _ => 0,
        };
    }
}
"#;

    let (unit, diag) = parse_source("PacketParser.rsharp", src);
    assert!(
        !diag.has_errors(),
        "Unexpected syntax errors: {}",
        diag.format_all()
    );

    let method = match &unit.types[0].members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected method"),
    };
    let body = method.body.as_ref().unwrap();
    assert_eq!(body.stmts.len(), 3);

    match &body.stmts[0] {
        Stmt::LocalVar { name, init, .. } => {
            assert_eq!(name, "header");
            assert!(matches!(init.kind, ExprKind::RangeSlice { .. }));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    match &body.stmts[1] {
        Stmt::LocalVar { name, init, .. } => {
            assert_eq!(name, "effective");
            assert!(matches!(init.kind, ExprKind::NullCoalesce { .. }));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    match &body.stmts[2] {
        Stmt::Return {
            value: Some(expr), ..
        } => {
            assert!(matches!(expr.kind, ExprKind::Switch { .. }));
        }
        other => panic!("Expected Return with Switch expr, got {:?}", other),
    }
}
