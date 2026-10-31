use rsharpc::analyze_workspace_with_preflight;
use rsharpc::diagnostics::DiagnosticCode;

#[test]
fn test_rsharp001_catches_service_class_field_mutation_outside_constructor() {
    let bad_service_src = r#"
namespace Commerce.Services;

public service class UserService
{
    private int _requestCounter;
    private readonly List<string> _auditLog;

    public UserService(List<string> auditLog)
    {
        _requestCounter = 0;
        _auditLog = auditLog;
    }

    public void RecordLogin(string user)
    {
        _requestCounter += 1;
        _auditLog.Add(user);
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Services/UserService.rsharp", bad_service_src)]);
    assert!(diag.has_errors());
    assert_eq!(
        diag.diagnostics.len(),
        2,
        "Expected RSHARP001 on both `_requestCounter += 1` and `_auditLog.Add(user)`, got: {}",
        diag.format_all()
    );

    assert_eq!(
        diag.diagnostics[0].code,
        DiagnosticCode::RSharp001ServiceMutation
    );
    assert!(diag.diagnostics[0].message.contains("_requestCounter"));
    assert!(diag.diagnostics[0].message.contains("UserService"));
    assert_eq!(diag.diagnostics[0].span.start_line, 17);

    assert_eq!(
        diag.diagnostics[1].code,
        DiagnosticCode::RSharp001ServiceMutation
    );
    assert!(diag.diagnostics[1].message.contains("_auditLog"));
    assert_eq!(diag.diagnostics[1].span.start_line, 18);
}

#[test]
fn test_rsharp002_catches_collection_mutation_during_foreach_iteration() {
    let aliasing_src = r#"
namespace Commerce.Orders;

public record Order(int Id, decimal Total);

public service class OrderBatchCleaner
{
    public void PruneEmptyOrders(List<Order> orders)
    {
        foreach (var order in orders)
        {
            if (order.Total <= 0.0m)
            {
                orders.Clear();
            }
        }
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Orders/OrderBatchCleaner.rsharp", aliasing_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);

    let err = &diag.diagnostics[0];
    assert_eq!(err.code, DiagnosticCode::RSharp002CollectionAliasing);
    assert!(err.message.contains("orders"));
    assert_eq!(err.span.filename, "Orders/OrderBatchCleaner.rsharp");
    assert_eq!(err.span.start_line, 14);
    assert!(err
        .quick_fix
        .as_deref()
        .unwrap()
        .contains("orders.ToList()"));
}

#[test]
fn test_rsharp003_catches_use_after_move_on_linear_disposable_resource() {
    let use_after_move_src = r#"
namespace Telemetry.Transport;

public class SocketHandle : IDisposable
{
    public intFd Fd;

    public void Dispose()
    {
    }
}

public record intFd(int Value);

public static class ChannelDispatcher
{
    public static void TakeOwnership([Moves] SocketHandle handle)
    {
    }

    public static void InspectSocket(SocketHandle handle)
    {
    }

    public static void DispatchTwice(SocketHandle socket)
    {
        TakeOwnership(socket);
        InspectSocket(socket);
    }
}
"#;

    let (_units, _symtab, diag) = analyze_workspace_with_preflight(&[(
        "Transport/ChannelDispatcher.rsharp",
        use_after_move_src,
    )]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);

    let err = &diag.diagnostics[0];
    assert_eq!(err.code, DiagnosticCode::RSharp003UseAfterMove);
    assert!(err.message.contains("socket"));
    assert!(
        err.message.contains("27:"),
        "Expected diagnostic to point to original move line 27, got: {}",
        err.message
    );
    assert_eq!(err.span.start_line, 28);
}

#[test]
fn test_clean_code_passes_preflight_verifier_with_zero_diagnostics() {
    let valid_src = r#"
namespace Commerce.Valid;

public record Item(int Id);

public shared class SharedSessionStore
{
    public void TouchSession(string sessionId)
    {
    }
}

public service class ValidCheckoutService
{
    private readonly SharedSessionStore _sessions;

    public ValidCheckoutService(SharedSessionStore sessions)
    {
        _sessions = sessions;
    }

    public int CountItems(List<Item> items)
    {
        var total = 0;
        foreach (var item in items)
        {
            total += item.Id;
        }
        return total;
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Valid/ValidCheckoutService.rsharp", valid_src)]);
    assert!(
        !diag.has_errors(),
        "Expected valid service and foreach read loop to pass preflight checks, got: {}",
        diag.format_all()
    );
}
