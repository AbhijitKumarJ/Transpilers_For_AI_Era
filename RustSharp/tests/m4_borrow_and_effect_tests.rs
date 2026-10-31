use rsharpc::analyze_workspace_pass2b;
use rsharpc::frontend::ast::{
    BorrowMode, CallerArgCoercion, EffectSignature, ExprKind, LinqOp, LinqTerminal, MemberDecl,
    PrimitiveLowering, Stmt,
};
use rsharpc::semantics::format_rust_param_type;

#[test]
fn test_bottom_up_interprocedural_mut_borrow_propagation_and_caller_coercion() {
    let checkout_src = r#"
namespace Commerce.Checkout;

public record Order(int Id, decimal Total);
public record ValidationError(string Reason);

public service class TaxCalculator
{
    public void RecordAudit(Order order)
    {
    }
}

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

    public void RunDemo()
    {
        var localOrder = new Order(101, 250.0m);
        ApplyCoupon(localOrder, "SAVE10");
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2b(&[("Features/Checkout/OrderHandler.rsharp", checkout_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let handler_id = symtab.fqn_to_symbol["Commerce.Checkout.OrderHandler"];
    let handler_sym = &symtab.types[&handler_id];

    let checkout_id = handler_sym.methods[0];
    let apply_coupon_id = handler_sym.methods[1];

    // 1. `ApplyCoupon` directly mutates `order.Total -= 10.0m` -> `MutBorrow` (&mut Order),
    //    while `code` is only read -> `ReadBorrow` (&str)
    let apply_sym = &symtab.methods[&apply_coupon_id];
    assert_eq!(apply_sym.inferred_self_borrow, BorrowMode::ReadBorrow);
    assert_eq!(apply_sym.params[0].inferred_borrow, BorrowMode::MutBorrow);
    assert_eq!(apply_sym.params[1].inferred_borrow, BorrowMode::ReadBorrow);
    assert_eq!(
        format_rust_param_type(
            &apply_sym.params[1].ty,
            apply_sym.params[1].inferred_borrow,
            &symtab
        ),
        "&str"
    );

    // 2. `Checkout` does NOT mutate `order` directly, but passes `order` to `ApplyCoupon`.
    //    Bottom-up interprocedural propagation upgrades `Checkout`'s `order` parameter to `MutBorrow`!
    let checkout_sym = &symtab.methods[&checkout_id];
    assert_eq!(
        checkout_sym.params[0].inferred_borrow,
        BorrowMode::MutBorrow,
        "Expected bottom-up interprocedural propagation to upgrade Checkout's 'order' to MutBorrow"
    );
    assert_eq!(
        checkout_sym.params[1].inferred_borrow,
        BorrowMode::ReadBorrow
    );

    // 3. Inspect `Checkout` body call-site coercions (`ApplyCoupon` gets `BorrowMutable`,
    //    and subsequent `_tax.RecordAudit(order)` gets `BorrowShared`)
    let handler_decl = &units[0].types[3];
    let checkout_decl = match &handler_decl.members[2] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected Checkout method"),
    };
    let checkout_stmts = &checkout_decl.body.as_ref().unwrap().stmts;

    match &checkout_stmts[1] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall { args, .. } => {
                assert_eq!(
                    args[0].expr.caller_coercion,
                    CallerArgCoercion::BorrowMutable
                );
                assert_eq!(
                    args[1].expr.caller_coercion,
                    CallerArgCoercion::BorrowShared
                );
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }

    match &checkout_stmts[2] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall { args, .. } => {
                assert_eq!(
                    args[0].expr.caller_coercion,
                    CallerArgCoercion::BorrowShared
                );
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }

    // 4. Inspect `RunDemo`: `var localOrder = new Order(...)` is passed to `ApplyCoupon`
    //    so `inferred_mut` is automatically set to `true` (`let mut local_order`)!
    let run_demo_decl = match &handler_decl.members[4] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected RunDemo method"),
    };
    match &run_demo_decl.body.as_ref().unwrap().stmts[0] {
        Stmt::LocalVar {
            name, inferred_mut, ..
        } => {
            assert_eq!(name, "localOrder");
            assert!(
                *inferred_mut,
                "Expected local variable passed to &mut parameter to be marked `inferred_mut = true`"
            );
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_checked_effect_throws_propagation_and_question_mark_injection() {
    let config_src = r#"
namespace Commerce.Config;

public record ParseError(string Message);

public static class ConfigLoader
{
    public static int ParsePort(string raw) throws ParseError
    {
        if (raw.IsEmpty)
            throw new ParseError("Port string cannot be empty");
        return 8080;
    }

    public static int ValidateAndDoublePort(string raw) throws ParseError
    {
        var port = ParsePort(raw);
        return port * 2;
    }

    public static int LoadDefaultPort(string input)
    {
        try
        {
            return ParsePort(input);
        }
        catch (ParseError err)
        {
            return 80;
        }
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2b(&[("Config/ConfigLoader.rsharp", config_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let loader_id = symtab.fqn_to_symbol["Commerce.Config.ConfigLoader"];
    let loader_sym = &symtab.types[&loader_id];

    let parse_port_id = loader_sym.methods[0];
    let validate_double_id = loader_sym.methods[1];
    let load_default_id = loader_sym.methods[2];

    // 1. `ParsePort` and `ValidateAndDoublePort` are `Fallible { error_type: ParseError }`
    assert!(matches!(
        symtab.methods[&parse_port_id].inferred_effect,
        EffectSignature::Fallible { .. }
    ));
    assert!(matches!(
        symtab.methods[&validate_double_id].inferred_effect,
        EffectSignature::Fallible { .. }
    ));

    // 2. `LoadDefaultPort` catches `ParseError` in `try / catch`, so its effect is `Infallible`!
    assert_eq!(
        symtab.methods[&load_default_id].inferred_effect,
        EffectSignature::Infallible
    );

    // 3. Inside `ValidateAndDoublePort`, the unguarded call `ParsePort(raw)` has
    //    `append_try_question_mark = true` (`parse_port(raw)?`)
    let loader_decl = &units[0].types[1];
    let validate_decl = match &loader_decl.members[1] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected ValidateAndDoublePort method"),
    };
    match &validate_decl.body.as_ref().unwrap().stmts[0] {
        Stmt::LocalVar { init, .. } => {
            assert!(
                init.append_try_question_mark,
                "Expected unguarded call to fallible ParsePort(raw) to have append_try_question_mark = true"
            );
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_linq_to_iterator_pipeline_fusion_and_primitive_lowering() {
    let linq_src = r#"
namespace Commerce.Analytics;

public record Order(int Id, decimal Total, bool IsActive);

public service class OrderAnalytics
{
    public List<int> GetHighValueIds(List<Order> orders)
    {
        var ids = orders
            .Where(o => o.IsActive && o.Total >= 100.0m)
            .Select(o => o.Id)
            .ToList();
        ids.Add(999);
        return ids;
    }

    public bool HasAnyActive(List<Order> orders)
    {
        return orders.Any(o => o.IsActive);
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2b(&[("Analytics/OrderAnalytics.rsharp", linq_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let analytics_id = symtab.fqn_to_symbol["Commerce.Analytics.OrderAnalytics"];
    let get_ids_id = symtab.types[&analytics_id].methods[0];
    let get_ids_sym = &symtab.methods[&get_ids_id];

    // `orders` parameter is only read by `.Where().Select().ToList()` -> `ReadBorrow` (`&[Order]`)
    assert_eq!(
        get_ids_sym.params[0].inferred_borrow,
        BorrowMode::ReadBorrow
    );
    assert_eq!(
        format_rust_param_type(
            &get_ids_sym.params[0].ty,
            get_ids_sym.params[0].inferred_borrow,
            &symtab
        ),
        "&[Order]"
    );

    let analytics_decl = &units[0].types[1];
    let get_ids_decl = match &analytics_decl.members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected GetHighValueIds method"),
    };
    let stmts = &get_ids_decl.body.as_ref().unwrap().stmts;

    // Statement 0: `var ids = orders.Where(...).Select(...).ToList();`
    // Verifies both `inferred_mut = true` (because `ids.Add(999)` mutates `ids` on the next line)
    // and `ExprKind::LinqChain` fusion!
    match &stmts[0] {
        Stmt::LocalVar {
            name,
            init,
            inferred_mut,
            ..
        } => {
            assert_eq!(name, "ids");
            assert!(
                *inferred_mut,
                "Expected `ids` to be marked `inferred_mut = true` due to `ids.Add(999)`"
            );
            match &init.kind {
                ExprKind::LinqChain(chain) => {
                    assert!(!chain.consumes_source);
                    assert_eq!(chain.ops.len(), 2);
                    assert!(matches!(chain.ops[0], LinqOp::Where { .. }));
                    assert!(matches!(chain.ops[1], LinqOp::Select { .. }));
                    assert_eq!(chain.terminal, LinqTerminal::ToList);
                }
                other => panic!("Expected fused ExprKind::LinqChain, got {:?}", other),
            }
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 1: `ids.Add(999);` -> resolved to `PrimitiveLowering::DirectSymbol { rust_path: "push" }`
    match &stmts[1] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall {
                primitive_lowering, ..
            } => {
                assert_eq!(
                    *primitive_lowering,
                    PrimitiveLowering::DirectSymbol {
                        rust_path: "push".to_string()
                    }
                );
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }
}
