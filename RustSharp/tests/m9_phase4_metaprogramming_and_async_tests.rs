//! Phase 4: Rust Metaprogramming, Attributes & Async Ecosystem Verification Suite.
//!
//! Tests for:
//! 1. Serde attribute lowering (`[JsonPropertyName]`, `[JsonIgnore]`, `[JsonRequired]`, `#[derive(Serialize, Deserialize)]`).
//! 2. Async/Await lowering (`async Task<T>` -> `async fn ... -> T`, `await expr` -> `expr.await`).
//! 3. Web routing & Axum interop (`[HttpGet]`, `[HttpPost]`, `[FromBody]`, `[FromRoute]`).
//! 4. Async streams (`IAsyncEnumerable<T>` -> `impl futures_core::Stream<Item = T>`).
//! 5. Automatic Cargo dependency synchronization for `serde`, `axum`, and `tokio`.

use rsharpc::analyze_workspace_pass2b;
use rsharpc::bindgen::CargoDependencySynchronizer;
use rsharpc::codegen::rs_ast_emitter::RustModuleEmitter;

#[test]
fn test_serde_attribute_lowering() {
    let code = r#"
namespace Commerce.Dtos;

public record UserDto(
    [JsonPropertyName("user_id")] int Id,
    [JsonPropertyName("email_address")] string Email,
    [JsonIgnore] string PasswordHash
);

public struct ProfileSettings
{
    [JsonPropertyName("theme_mode")]
    public string Theme;

    [JsonRequired]
    public bool NotificationsEnabled;
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("user_dto.rsharp", code)]);
    assert!(!diag.has_errors(), "Diagnostics:\n{}", diag.format_all());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) =
        emitter.emit_namespace_module(&units[0].namespace, &type_refs, "user_dto.rs");

    // Assert Serde derive emission
    assert!(emitted
        .contains("#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]"));

    // Assert primary constructor parameter serde annotations
    assert!(emitted.contains("#[serde(rename = \"user_id\")]"));
    assert!(emitted.contains("pub id: i32,"));
    assert!(emitted.contains("#[serde(rename = \"email_address\")]"));
    assert!(emitted.contains("pub email: String,"));
    assert!(emitted.contains("#[serde(skip)]"));
    assert!(emitted.contains("pub password_hash: String,"));

    // Assert struct field serde annotations
    assert!(emitted.contains("#[serde(rename = \"theme_mode\")]"));
    assert!(emitted.contains("pub theme: String,"));
    assert!(emitted.contains("#[serde(default)]"));
    assert!(emitted.contains("pub notifications_enabled: bool,"));
}

#[test]
fn test_async_task_unwrapping_and_await_lowering() {
    let code = r#"
namespace Commerce.Services;

public record Order(int Id, decimal Total);
public record PaymentReceipt(string TxId, bool Success);

public class PaymentError { }

public service class PaymentClient
{
    public async Task<PaymentReceipt> ChargeAsync(decimal amount) throws PaymentError
    {
        return new PaymentReceipt("tx_12345", true);
    }
}

public service class OrderProcessor
{
    private readonly PaymentClient _client;

    public OrderProcessor(PaymentClient client) => _client = client;

    public async Task<PaymentReceipt> CheckoutAsync(Order order) throws PaymentError
    {
        var receipt = await _client.ChargeAsync(order.Total);
        return receipt;
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("orders.rsharp", code)]);
    assert!(!diag.has_errors(), "Diagnostics:\n{}", diag.format_all());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "orders.rs");

    // Assert async fn signature and Task<T> unwrap to Result<PaymentReceipt, PaymentError>
    assert!(emitted.contains(
        "pub async fn charge_async(&self, amount: Decimal) -> Result<PaymentReceipt, PaymentError>"
    ));
    assert!(emitted.contains(
        "pub async fn checkout_async(&self, order: &Order) -> Result<PaymentReceipt, PaymentError>"
    ));

    // Assert await expression emission
    assert!(emitted.contains(".charge_async(order.total).await?"));
}

#[test]
fn test_web_routing_axum_attributes_and_extractors() {
    let code = r#"
namespace Commerce.Api;

public record CreateOrderRequest(int ItemCount, decimal Total);
public record OrderResponse(string OrderId, string Status);

public class ApiError { }

public service class OrderController
{
    [HttpGet("/api/orders/{customerId}/{orderId}")]
    public async Task<OrderResponse> GetOrder(
        [FromRoute] string customerId,
        [FromRoute] string orderId
    ) throws ApiError
    {
        return new OrderResponse(orderId, "Completed");
    }

    [HttpPost("/api/orders")]
    public async Task<OrderResponse> CreateOrder(
        [FromBody] CreateOrderRequest request
    ) throws ApiError
    {
        return new OrderResponse("ord_999", "Created");
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("controller.rsharp", code)]);
    assert!(!diag.has_errors(), "Diagnostics:\n{}", diag.format_all());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) =
        emitter.emit_namespace_module(&units[0].namespace, &type_refs, "controller.rs");

    // Assert Axum route attributes with :param syntax
    assert!(emitted.contains("#[axum::routing::get(\"/api/orders/:customerId/:orderId\")]"));
    assert!(emitted.contains("#[axum::routing::post(\"/api/orders\")]"));

    // Assert Axum extractors: Path and Json
    assert!(emitted.contains("customer_id: axum::extract::Path<String>"));
    assert!(emitted.contains("order_id: axum::extract::Path<String>"));
    assert!(emitted.contains("request: axum::extract::Json<CreateOrderRequest>"));
}

#[test]
fn test_async_streams_iasync_enumerable_lowering() {
    let code = r#"
namespace Commerce.Telemetry;

public service class MetricStreamer
{
    public IAsyncEnumerable<int> StreamHeartbeats()
    {
        return null;
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("streamer.rsharp", code)]);
    assert!(!diag.has_errors(), "Diagnostics:\n{}", diag.format_all());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) =
        emitter.emit_namespace_module(&units[0].namespace, &type_refs, "streamer.rs");

    // Assert IAsyncEnumerable<int> lowers to `impl futures_core::Stream<Item = i32>`
    assert!(emitted
        .contains("pub fn stream_heartbeats(&self) -> impl futures_core::Stream<Item = i32>"));
}

#[test]
fn test_cargo_dependencies_auto_synced_for_phase4() {
    let code = r#"
namespace Commerce.Web;

public record ProductDto([JsonPropertyName("sku")] string Sku);

public service class ProductController
{
    [HttpGet("/products")]
    public async Task<ProductDto> GetProducts()
    {
        return new ProductDto("SKU-1");
    }
}
"#;

    let (units, _symtab, diag) = analyze_workspace_pass2b(&[("web.rsharp", code)]);
    assert!(!diag.has_errors());

    let deps = CargoDependencySynchronizer::discover_dependencies(&units);
    assert_eq!(deps.get("serde"), Some(&"1.0".to_string()));
    assert_eq!(deps.get("axum"), Some(&"0.7".to_string()));
    assert_eq!(deps.get("tokio"), Some(&"1.0".to_string()));
}
