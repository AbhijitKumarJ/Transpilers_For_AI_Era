use rsharpc::analyze_workspace_pass2b;
use rsharpc::codegen::RustExprEmitter;
use rsharpc::frontend::ast::{ExprKind, LinqOp, LinqTerminal, MemberDecl, PrimitiveLowering, Stmt};

#[test]
fn test_phase2_math_and_primitive_intrinsics_lowering() {
    let src = r#"
namespace TestApp;

public class MathTest
{
    public void Run()
    {
        var m1 = Math.Min(10, 20);
        var m2 = Math.Max(10, 20);
        var absVal = Math.Abs(-50);
        var clamped = Math.Clamp(15, 0, 10);
        var num = Int32.Parse("42");
        var maybeNum = Int32.TryParse("42");
        Console.Write("Calculating...");
        Console.WriteErrorLine("Warning: low memory");
    }
}
"#;

    let (units, _symtab, diag) = analyze_workspace_pass2b(&[("MathTest.rsharp", src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let type_decl = &units[0].types[0];
    let method = match &type_decl.members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected Run method"),
    };
    let stmts = &method.body.as_ref().unwrap().stmts;

    // Check that Math.Min was lowered to an InlineTemplate
    match &stmts[0] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::MethodCall {
                primitive_lowering, ..
            } => {
                assert!(matches!(
                    primitive_lowering,
                    PrimitiveLowering::InlineTemplate { .. }
                ));
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Check that Int32.Parse was lowered to InlineTemplate parse::<i32>()
    match &stmts[4] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::MethodCall {
                primitive_lowering, ..
            } => match primitive_lowering {
                PrimitiveLowering::InlineTemplate { template } => {
                    assert!(template.contains("parse::<i32>().unwrap()"));
                }
                other => panic!("Expected InlineTemplate, got {:?}", other),
            },
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Check that Console.Write was lowered to print!
    match &stmts[6] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall {
                primitive_lowering, ..
            } => match primitive_lowering {
                PrimitiveLowering::InlineTemplate { template } => {
                    assert!(template.contains("print!"));
                }
                other => panic!("Expected InlineTemplate, got {:?}", other),
            },
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }

    // Check that Console.WriteErrorLine was lowered to eprintln!
    match &stmts[7] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall {
                primitive_lowering, ..
            } => match primitive_lowering {
                PrimitiveLowering::InlineTemplate { template } => {
                    assert!(template.contains("eprintln!"));
                }
                other => panic!("Expected InlineTemplate, got {:?}", other),
            },
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }
}

#[test]
fn test_phase2_extended_linq_operators_fusion_and_emission() {
    let src = r#"
namespace TestApp;

public record Item(int Id, decimal Price);

public class LinqExtTest
{
    public void TestExtensions(List<Item> items)
    {
        var sorted = items.OrderBy(i => i.Price).ToList();
        var descSorted = items.OrderByDescending(i => i.Price).ToList();
        var reversed = items.Reverse().ToList();
        var distinct = items.Distinct().ToList();
        var firstItem = items.First();
        var firstMatch = items.First(i => i.Id > 5);
        var lastItem = items.Last();
        var total = items.Select(i => i.Id).Aggregate(0, (acc, id) => acc + id);
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("LinqExtTest.rsharp", src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let type_decl = &units[0].types[1];
    let method = match &type_decl.members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected TestExtensions method"),
    };
    let stmts = &method.body.as_ref().unwrap().stmts;

    // Statement 0: OrderBy -> ToList
    let mut emitter = RustExprEmitter::new(&symtab, None);
    match &stmts[0] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::LinqChain(chain) => {
                assert_eq!(chain.ops.len(), 1);
                assert!(matches!(
                    chain.ops[0],
                    LinqOp::OrderBy {
                        descending: false,
                        ..
                    }
                ));
                assert_eq!(chain.terminal, LinqTerminal::ToList);
                let emitted = emitter.emit_expr(init);
                assert!(emitted.contains("sort_by_key"));
            }
            other => panic!("Expected LinqChain, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 1: OrderByDescending -> ToList
    match &stmts[1] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::LinqChain(chain) => {
                assert!(matches!(
                    chain.ops[0],
                    LinqOp::OrderBy {
                        descending: true,
                        ..
                    }
                ));
                let emitted = emitter.emit_expr(init);
                assert!(emitted.contains("sort_by_key") && emitted.contains("reverse()"));
            }
            other => panic!("Expected LinqChain, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 2: Reverse -> ToList
    match &stmts[2] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::LinqChain(chain) => {
                assert!(matches!(chain.ops[0], LinqOp::Reverse));
                let emitted = emitter.emit_expr(init);
                assert!(emitted.contains("rev().collect::<Vec<_>>()"));
            }
            other => panic!("Expected LinqChain, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 4: First() terminal
    match &stmts[4] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::LinqChain(chain) => {
                assert!(matches!(
                    chain.terminal,
                    LinqTerminal::First { predicate: None }
                ));
                let emitted = emitter.emit_expr(init);
                assert!(emitted.contains("next().cloned().unwrap()"));
            }
            other => panic!("Expected LinqChain, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 5: First(predicate) terminal
    match &stmts[5] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::LinqChain(chain) => {
                assert!(matches!(
                    chain.terminal,
                    LinqTerminal::First { predicate: Some(_) }
                ));
                let emitted = emitter.emit_expr(init);
                assert!(emitted.contains("find(") && emitted.contains("unwrap()"));
            }
            other => panic!("Expected LinqChain, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 7: Aggregate terminal
    match &stmts[7] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::LinqChain(chain) => {
                assert!(matches!(chain.terminal, LinqTerminal::Aggregate { .. }));
                let emitted = emitter.emit_expr(init);
                assert!(emitted.contains("fold(0,"));
            }
            other => panic!("Expected LinqChain, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_phase2_string_utilities_lowering() {
    let src = r#"
namespace TestApp;

public class StringUtilsTest
{
    public void CheckStrings(List<string> parts, string input)
    {
        var joined = String.Join(", ", parts);
        var empty = String.IsNullOrEmpty(input);
        var whitespace = String.IsNullOrWhiteSpace(input);
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("StringUtilsTest.rsharp", src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let type_decl = &units[0].types[0];
    let method = match &type_decl.members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected CheckStrings method"),
    };
    let stmts = &method.body.as_ref().unwrap().stmts;

    let mut emitter = RustExprEmitter::new(&symtab, None);

    // Statement 0: String.Join -> parts.join(", ")
    match &stmts[0] {
        Stmt::LocalVar { init, .. } => {
            let emitted = emitter.emit_expr(init);
            assert!(emitted.contains(".join("));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 1: String.IsNullOrEmpty -> input.is_empty()
    match &stmts[1] {
        Stmt::LocalVar { init, .. } => {
            let emitted = emitter.emit_expr(init);
            assert!(emitted.contains(".is_empty()"));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 2: String.IsNullOrWhiteSpace -> input.trim().is_empty()
    match &stmts[2] {
        Stmt::LocalVar { init, .. } => {
            let emitted = emitter.emit_expr(init);
            assert!(emitted.contains(".trim().is_empty()"));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}
