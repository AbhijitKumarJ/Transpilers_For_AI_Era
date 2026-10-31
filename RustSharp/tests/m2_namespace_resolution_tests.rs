use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

use rsharpc::analyze_workspace_pass1;
use rsharpc::diagnostics::DiagnosticCode;
use rsharpc::frontend::ast::{FieldStorageMode, TypeKind};
use rsharpc::project::load_rsproj;

#[test]
fn test_decoupled_folders_and_circular_cross_file_type_resolution() {
    // Two `.rsharp` files in completely different physical folders (`Domain/Customer.rsharp`
    // and `Features/Sales/Order.rsharp`) that reference each other's types circularly.
    let customer_src = r#"
namespace Commerce.Domain;

using Commerce.Sales;

public record Customer(int Id, string Name, List<Order> RecentOrders);

public service class CustomerDirectory
{
    public Order? FindLatestOrder(Customer customer)
    {
        return null;
    }
}
"#;

    let order_src = r#"
namespace Commerce.Sales;

using Commerce.Domain;

public record Order(int OrderId, Customer Buyer, decimal Amount);

public service class OrderProcessor
{
    private readonly CustomerDirectory _directory;

    public OrderProcessor(CustomerDirectory directory) => _directory = directory;

    public Customer GetOrderBuyer(Order order) => order.Buyer;
}
"#;

    let files = [
        ("src/Domain/Entities/Customer.rsharp", customer_src),
        ("src/Features/Sales/Handlers/Order.rsharp", order_src),
    ];

    let (_units, symtab, diag) = analyze_workspace_pass1(&files);
    assert!(
        !diag.has_errors(),
        "Expected circular cross-file references to resolve cleanly, got: {}",
        diag.format_all()
    );

    // Verify both namespaces were registered
    let domain_ns = vec!["Commerce".to_string(), "Domain".to_string()];
    let sales_ns = vec!["Commerce".to_string(), "Sales".to_string()];
    assert!(symtab.namespaces.contains_key(&domain_ns));
    assert!(symtab.namespaces.contains_key(&sales_ns));

    // Verify Customer and Order symbol IDs
    let customer_id = symtab
        .fqn_to_symbol
        .get("Commerce.Domain.Customer")
        .copied()
        .expect("Customer symbol missing");
    let order_id = symtab
        .fqn_to_symbol
        .get("Commerce.Sales.Order")
        .copied()
        .expect("Order symbol missing");
    let directory_id = symtab
        .fqn_to_symbol
        .get("Commerce.Domain.CustomerDirectory")
        .copied()
        .expect("CustomerDirectory symbol missing");
    let processor_id = symtab
        .fqn_to_symbol
        .get("Commerce.Sales.OrderProcessor")
        .copied()
        .expect("OrderProcessor symbol missing");

    // Verify Order's `Buyer` primary constructor field resolved directly to `Customer`
    let order_sym = &symtab.types[&order_id];
    assert_eq!(order_sym.fields.len(), 3);
    let buyer_field = &symtab.fields[&order_sym.fields[1]];
    assert_eq!(buyer_field.name, "Buyer");
    assert_eq!(buyer_field.resolved_type_id, Some(customer_id));

    // Verify OrderProcessor's `_directory` field resolved to `CustomerDirectory` and has `ArcShared` storage
    let processor_sym = &symtab.types[&processor_id];
    assert_eq!(processor_sym.kind, TypeKind::ServiceClass);
    let dir_field = &symtab.fields[&processor_sym.fields[0]];
    assert_eq!(dir_field.name, "_directory");
    assert_eq!(dir_field.resolved_type_id, Some(directory_id));
    assert_eq!(dir_field.storage_mode, FieldStorageMode::ArcShared);
    assert!(dir_field.is_readonly);

    // Verify CustomerDirectory.FindLatestOrder return type resolved to `Order`
    let dir_sym = &symtab.types[&directory_id];
    let find_method = &symtab.methods[&dir_sym.methods[0]];
    assert_eq!(find_method.name, "FindLatestOrder");
    assert_eq!(find_method.resolved_return_type_id, Some(order_id));
    assert_eq!(find_method.params[0].resolved_type_id, Some(customer_id));
}

#[test]
fn test_virtual_namespace_aggregation_across_multiple_files() {
    // Three files in different subdirectories all declaring `namespace Commerce.Checkout;`
    let file_a = r#"
namespace Commerce.Checkout;

public record CartItem(int Sku, int Quantity);
"#;

    let file_b = r#"
namespace Commerce.Checkout;

public record CheckoutReceipt(int ReceiptId, List<CartItem> Items);
"#;

    let file_c = r#"
namespace Commerce.Checkout;

public partial service class CheckoutCoordinator
{
    public CheckoutReceipt BuildReceipt(List<CartItem> items) => new CheckoutReceipt(1, items);
}
"#;

    let file_d = r#"
namespace Commerce.Checkout;

public partial service class CheckoutCoordinator
{
    public int CountItems(CheckoutReceipt receipt) => 0;
}
"#;

    let files = [
        ("Features/Cart/CartItem.rsharp", file_a),
        ("Features/Receipts/CheckoutReceipt.rsharp", file_b),
        ("Services/CheckoutCoordinator.Part1.rsharp", file_c),
        ("Services/CheckoutCoordinator.Part2.rsharp", file_d),
    ];

    let (_units, symtab, diag) = analyze_workspace_pass1(&files);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let plans = symtab.build_namespace_module_plans();
    assert_eq!(plans.len(), 1);

    let plan = &plans[0];
    assert_eq!(plan.namespace, vec!["Commerce", "Checkout"]);
    assert_eq!(plan.rust_mod_segments, vec!["commerce", "checkout"]);
    assert_eq!(plan.target_rs_file, "src/commerce/checkout.rs");

    // Partial class `CheckoutCoordinator` should be merged into a single TypeSymbol (3 unique types total)
    assert_eq!(plan.type_ids.len(), 3);

    let coord_id = symtab.fqn_to_symbol["Commerce.Checkout.CheckoutCoordinator"];
    let coord_sym = &symtab.types[&coord_id];
    assert_eq!(coord_sym.methods.len(), 2);
    assert_eq!(coord_sym.source_files.len(), 2);
}

#[test]
fn test_reports_unresolved_symbol_diagnostic_with_exact_span() {
    let bad_src = r#"
namespace Commerce.Orders;

public service class BrokenService
{
    public NonExistentDto LoadItem(int id)
    {
        return null;
    }
}
"#;

    let (_units, _symtab, diag) = analyze_workspace_pass1(&[("BrokenService.rsharp", bad_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);

    let err = &diag.diagnostics[0];
    assert_eq!(err.code, DiagnosticCode::UnresolvedSymbol);
    assert!(err.message.contains("NonExistentDto"));
    assert_eq!(err.span.filename, "BrokenService.rsharp");
    assert_eq!(err.span.start_line, 6);
}

#[test]
fn test_rsproj_loader_discovers_rsharp_stubs_and_colocated_rs_files() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let temp_root = std::env::temp_dir().join(format!("rsharp_m2_test_{}", unique));
    let ingest_dir = temp_root.join("Ingest");
    let features_dir = temp_root.join("Features").join("Checkout");
    fs::create_dir_all(&ingest_dir).unwrap();
    fs::create_dir_all(&features_dir).unwrap();

    let rsproj_xml = r#"
<Project Sdk="RustSharp.Sdk">
  <PropertyGroup>
    <AssemblyName>Commerce.Core</AssemblyName>
    <Version>0.2.0</Version>
    <RustEdition>2021</RustEdition>
    <OutputPath>build/cargo_out</OutputPath>
  </PropertyGroup>
  <ItemGroup>
    <CargoCrate Include="rust_decimal" Version="1.36" />
    <CargoCrate Include="tokio" Version="1.40" />
  </ItemGroup>
</Project>
"#;

    let rsproj_path = temp_root.join("Commerce.Core.rsproj");
    fs::write(&rsproj_path, rsproj_xml).unwrap();
    fs::write(
        temp_root.join("RustSharp.Core.d.rsharp"),
        "namespace RustSharp.Core;\n[MapsTo(\"std::vec::Vec\")]\npublic primitive class List<T> { }\n",
    )
    .unwrap();
    fs::write(
        features_dir.join("OrderHandler.rsharp"),
        "namespace Commerce.Checkout;\npublic record Order(int Id);\n",
    )
    .unwrap();
    fs::write(
        ingest_dir.join("PacketHeader.rsharp"),
        "namespace Commerce.Ingest;\npublic partial struct PacketHeader { public uint Magic; }\n",
    )
    .unwrap();
    fs::write(
        ingest_dir.join("PacketHeader.rs"),
        "// Co-located raw Rust implementation\n",
    )
    .unwrap();

    let cfg = load_rsproj(&rsproj_path, None).expect("Failed to load .rsproj");
    assert_eq!(cfg.name, "commerce_core");
    assert_eq!(cfg.version, "0.2.0");
    assert_eq!(cfg.edition, "2021");
    assert_eq!(cfg.cargo_dependencies.len(), 2);
    assert_eq!(
        cfg.cargo_dependencies[0],
        ("rust_decimal".to_string(), "1.36".to_string())
    );
    assert_eq!(cfg.stub_files.len(), 1);
    assert_eq!(cfg.rsharp_files.len(), 2);
    assert_eq!(cfg.colocated_rs_files.len(), 1);

    let _ = fs::remove_dir_all(&temp_root);
}
