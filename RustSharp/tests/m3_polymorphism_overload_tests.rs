use rsharpc::analyze_workspace_pass2a;
use rsharpc::diagnostics::DiagnosticCode;
use rsharpc::frontend::ast::{
    BorrowMode, ExprKind, FieldStorageMode, LiteralValue, MemberDecl, PolymorphismStrategy, Stmt,
};

#[test]
fn test_closed_world_enum_dispatch_and_flattened_base_struct_lowering() {
    let payment_src = r#"
namespace Commerce.Payments;

public extensible interface IPaymentPlugin
{
    string PluginId();
}

public abstract class Payment
{
    public decimal Amount { get; set; }
    public abstract string Summarize();
}

public class CardPayment : Payment
{
    public string LastFour { get; set; }
    public override string Summarize() => $"Card *{LastFour}: {Amount}";
}

public class CryptoPayment : Payment
{
    public string WalletHash { get; set; }
    public override string Summarize() => $"Wallet {WalletHash}: {Amount}";
}
"#;

    let (_units, symtab, diag) =
        analyze_workspace_pass2a(&[("Features/Payments/PaymentHierarchy.rsharp", payment_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let plugin_id = symtab.fqn_to_symbol["Commerce.Payments.IPaymentPlugin"];
    let payment_id = symtab.fqn_to_symbol["Commerce.Payments.Payment"];
    let card_id = symtab.fqn_to_symbol["Commerce.Payments.CardPayment"];
    let crypto_id = symtab.fqn_to_symbol["Commerce.Payments.CryptoPayment"];

    // 1. `extensible interface IPaymentPlugin` -> `PolymorphismStrategy::OpenTrait`
    assert_eq!(
        symtab.types[&plugin_id].inferred_polymorphism,
        PolymorphismStrategy::OpenTrait
    );

    // 2. Closed-world `abstract class Payment` -> `PolymorphismStrategy::ClosedWorldEnum`
    //    containing `CardPayment` and `CryptoPayment` variants (zero dynamic vtable heap boxing!)
    assert_eq!(
        symtab.types[&payment_id].inferred_polymorphism,
        PolymorphismStrategy::ClosedWorldEnum {
            variants: vec![card_id, crypto_id]
        }
    );

    // 3. `CardPayment` and `CryptoPayment` -> `PolymorphismStrategy::FlattenedSubStruct`
    //    embedding `Payment` for `Deref`/`DerefMut` state reuse
    assert_eq!(
        symtab.types[&card_id].inferred_polymorphism,
        PolymorphismStrategy::FlattenedSubStruct {
            base_type: payment_id
        }
    );
    assert_eq!(
        symtab.types[&crypto_id].inferred_polymorphism,
        PolymorphismStrategy::FlattenedSubStruct {
            base_type: payment_id
        }
    );
}

#[test]
fn test_static_compile_time_overload_disambiguation_and_default_arg_injection() {
    let repo_src = r#"
namespace Commerce.Users;

public record User(int Id, string Email);

public service class UserRepository
{
    public User Find(int id) => new User(id, "id@example.com");

    public User Find(string email, bool activeOnly = true) => new User(1, email);

    public User RunLookup()
    {
        var byId = Find(42);
        var byEmail = Find("alice@example.com");
        return byEmail;
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2a(&[("Users/UserRepository.rsharp", repo_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let repo_id = symtab.fqn_to_symbol["Commerce.Users.UserRepository"];
    let repo_sym = &symtab.types[&repo_id];

    let find_int_id = repo_sym.methods[0];
    let find_email_id = repo_sym.methods[1];

    // Verify static compile-time disambiguated Rust method names
    assert_eq!(
        symtab.methods[&find_int_id].disambiguated_rust_name,
        "find_by_id"
    );
    assert_eq!(
        symtab.methods[&find_email_id].disambiguated_rust_name,
        "find_by_email"
    );

    // Verify call sites inside `RunLookup()` resolved statically to their exact overload SymbolIds
    // and that `Find("alice@example.com")` had the default `true` argument injected automatically!
    let repo_decl = &units[0].types[1];
    let run_lookup = match &repo_decl.members[2] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected RunLookup method"),
    };
    let stmts = &run_lookup.body.as_ref().unwrap().stmts;

    // `var byId = Find(42);`
    match &stmts[0] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::MethodCall {
                resolved_overload,
                args,
                ..
            } => {
                assert_eq!(*resolved_overload, Some(find_int_id));
                assert_eq!(args.len(), 1);
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // `var byEmail = Find("alice@example.com");` -> resolves to `find_email_id` + injects `true`
    match &stmts[1] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::MethodCall {
                resolved_overload,
                args,
                ..
            } => {
                assert_eq!(*resolved_overload, Some(find_email_id));
                assert_eq!(
                    args.len(),
                    2,
                    "Expected omitted default parameter `activeOnly = true` to be injected"
                );
                assert_eq!(
                    args[1].expr.kind,
                    ExprKind::Literal(LiteralValue::Bool(true))
                );
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_service_arc_shared_rwlock_and_disposable_drop_archetypes() {
    let archetype_src = r#"
namespace Commerce.Infrastructure;

public shared class MetricsRegistry
{
    private int _requestCount;
}

public service class AuditLogger
{
    private readonly MetricsRegistry _metrics;

    public AuditLogger(MetricsRegistry metrics) => _metrics = metrics;
}

public class DbTransaction : IDisposable
{
    public void Dispose()
    {
    }
}
"#;

    let (_units, symtab, diag) =
        analyze_workspace_pass2a(&[("Infra/Archetypes.rsharp", archetype_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let metrics_id = symtab.fqn_to_symbol["Commerce.Infrastructure.MetricsRegistry"];
    let logger_id = symtab.fqn_to_symbol["Commerce.Infrastructure.AuditLogger"];
    let tx_id = symtab.fqn_to_symbol["Commerce.Infrastructure.DbTransaction"];

    // `shared class MetricsRegistry` field uses `RwLockShared`
    let req_field_id = symtab.types[&metrics_id].fields[0];
    assert_eq!(
        symtab.fields[&req_field_id].storage_mode,
        FieldStorageMode::RwLockShared
    );

    // `service class AuditLogger` field uses `ArcShared`
    let metrics_field_id = symtab.types[&logger_id].fields[0];
    assert_eq!(
        symtab.fields[&metrics_field_id].storage_mode,
        FieldStorageMode::ArcShared
    );

    // `DbTransaction : IDisposable` sets `has_disposable_drop = true` and `Dispose(&mut self)`
    let tx_sym = &symtab.types[&tx_id];
    assert!(tx_sym.has_disposable_drop);
    let dispose_id = tx_sym.methods[0];
    assert_eq!(
        symtab.methods[&dispose_id].inferred_self_borrow,
        BorrowMode::MutBorrow
    );
}

#[test]
fn test_enforces_private_access_modifier_across_classes() {
    let bad_access_src = r#"
namespace Commerce.Security;

public class Vault
{
    private string _secretKey;
    public string PublicLabel { get; private set; }
}

public service class VaultInspector
{
    public void Tamper(Vault v)
    {
        v.PublicLabel = "Hacked";
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_pass2a(&[("Security/Vault.rsharp", bad_access_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);
    assert_eq!(diag.diagnostics[0].code, DiagnosticCode::AccessViolation);
    assert!(diag.diagnostics[0].message.contains("PublicLabel.set"));
}
