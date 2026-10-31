use rsharpc::analyze_workspace_pass2b;
use rsharpc::codegen::RustModuleEmitter;

#[test]
fn test_golden_record_dto_emission() {
    let src = r#"
namespace Domain;

public record Order(int Id, decimal Total, string CustomerEmail);
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("Domain/Order.rsharp", src)]);
    assert!(!diag.has_errors());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "test.rs");

    assert!(emitted.contains("#[derive(Clone, Debug, PartialEq)]"));
    assert!(emitted.contains("pub struct Order {"));
    assert!(emitted.contains("pub id: i32,"));
    assert!(emitted.contains("pub total: Decimal,"));
    assert!(emitted.contains("pub customer_email: String,"));
}

#[test]
fn test_golden_service_class_arc_emission() {
    let src = r#"
namespace Services;

public service class Database
{
    public void Connect() { }
}

public service class OrderService
{
    private readonly Database _db;

    public OrderService(Database db)
    {
        _db = db;
    }

    public void Process()
    {
        _db.Connect();
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("Services/OrderService.rsharp", src)]);
    assert!(!diag.has_errors());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "test.rs");

    assert!(emitted.contains("pub struct OrderService {"));
    assert!(emitted.contains("db: Arc<Database>,"));
    assert!(emitted.contains("pub fn new(db: std::sync::Arc<Database>) -> Self {"));
    assert!(emitted.contains("pub fn process(&self) {"));
}

#[test]
fn test_golden_state_inheritance_deref_flattening() {
    let src = r#"
namespace Models;

public class EntityBase
{
    public int Id { get; set; }
    public string CreatedAt { get; set; }
}

public class Customer : EntityBase
{
    public string Name { get; set; }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("Models/Customer.rsharp", src)]);
    assert!(!diag.has_errors());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "test.rs");

    assert!(emitted.contains("pub struct Customer {"));
    assert!(emitted.contains("pub base: EntityBase,"));
    assert!(emitted.contains("pub name: String,"));
    assert!(emitted.contains("impl std::ops::Deref for Customer {"));
    assert!(emitted.contains("type Target = EntityBase;"));
    assert!(emitted.contains("&self.base"));
    assert!(emitted.contains("impl std::ops::DerefMut for Customer {"));
    assert!(emitted.contains("&mut self.base"));
}

#[test]
fn test_golden_closed_world_enum_dispatch() {
    let src = r#"
namespace Billing;

public abstract class Payment
{
    public decimal Amount { get; set; }
    public abstract string GetDetails();
}

public class CardPayment : Payment
{
    public string CardNumber { get; set; }
    public override string GetDetails() => $"Card: {CardNumber}";
}

public class CryptoPayment : Payment
{
    public string Wallet { get; set; }
    public override string GetDetails() => $"Crypto: {Wallet}";
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("Billing/Payment.rsharp", src)]);
    assert!(!diag.has_errors());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "test.rs");

    assert!(emitted.contains("pub enum Payment {"));
    assert!(emitted.contains("Card(CardPayment),"));
    assert!(emitted.contains("Crypto(CryptoPayment),"));
    assert!(emitted.contains("match self {"));
}

#[test]
fn test_golden_checked_effects_and_question_mark() {
    let src = r#"
namespace Utils;

public record FileError(string Message);

public class ConfigReader
{
    public string ReadFile(string path) throws FileError
    {
        if (path.Length == 0)
            throw new FileError("Path cannot be empty");
        return "content";
    }

    public string LoadConfig(string path) throws FileError
    {
        return ReadFile(path);
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("Utils/ConfigReader.rsharp", src)]);
    assert!(!diag.has_errors());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "test.rs");

    assert!(emitted.contains("pub fn read_file(&self, path: &str) -> Result<String, FileError> {"));
    assert!(emitted.contains("return Err(FileError {"));
    assert!(emitted.contains("Ok(\"content\".to_string())"));
    assert!(emitted.contains("Ok(self.read_file(path)?)"));
}

#[test]
fn test_golden_fused_linq_pipeline() {
    let src = r#"
namespace Analytics;

public record Metric(int Value, bool IsValid);

public class Reporter
{
    public List<int> GetValidTopValues(List<Metric> metrics)
    {
        return metrics
            .Where(m => m.IsValid)
            .Select(m => m.Value)
            .Take(10)
            .ToList();
    }
}
"#;

    let (units, symtab, diag) = analyze_workspace_pass2b(&[("Analytics/Reporter.rsharp", src)]);
    assert!(!diag.has_errors());

    let mut emitter = RustModuleEmitter::new(&symtab);
    let type_refs: Vec<&rsharpc::frontend::ast::TypeDecl> = units[0].types.iter().collect();
    let (emitted, _) = emitter.emit_namespace_module(&units[0].namespace, &type_refs, "test.rs");

    assert!(emitted.contains("metrics.iter()"));
    assert!(emitted.contains("filter("));
    assert!(emitted.contains("map("));
    assert!(emitted.contains("take(10 as usize)"));
    assert!(emitted.contains("collect::<Vec<_>>()"));
}
