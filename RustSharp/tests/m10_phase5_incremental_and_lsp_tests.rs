//! Phase 5 Test Suite: Developer Experience, Incremental Build Cache & Language Server Protocol (LSP).

use rsharpc::lsp::{JsonRpcMessage, LspServer};
use rsharpc::project::{compute_sha256, IncrementalBuildCache};

#[test]
fn test_pure_rust_sha256_computation() {
    // NIST Standard Test Vectors
    assert_eq!(
        compute_sha256(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );

    assert_eq!(
        compute_sha256(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );

    assert_eq!(
        compute_sha256(b"The quick brown fox jumps over the lazy dog"),
        "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592"
    );
}

#[test]
fn test_incremental_cache_serialization_and_skip() {
    let mut cache = IncrementalBuildCache::default();
    let inputs = [
        (
            "Models/Order.rsharp",
            "namespace Commerce; record class Order(string Id);",
        ),
        (
            "Services/OrderService.rsharp",
            "namespace Commerce; class OrderService {}",
        ),
    ];

    cache.record_inputs(&inputs);
    cache.emitted_modules.insert(
        "src/commerce.rs".to_string(),
        "pub struct Order { pub id: String }\npub struct OrderService;".to_string(),
    );
    cache.cargo_toml = "[package]\nname = \"commerce\"\nversion = \"0.1.0\"\n".to_string();
    cache.lib_rs = "pub mod commerce;\n".to_string();

    // Verify cache is up to date when inputs match
    assert!(cache.is_up_to_date(&inputs));

    // Verify cache detects modification
    let modified_inputs = [
        (
            "Models/Order.rsharp",
            "namespace Commerce; record class Order(string Id, decimal Total);",
        ),
        (
            "Services/OrderService.rsharp",
            "namespace Commerce; class OrderService {}",
        ),
    ];
    assert!(!cache.is_up_to_date(&modified_inputs));

    // Verify cache detects file removal
    let fewer_inputs = [(
        "Models/Order.rsharp",
        "namespace Commerce; record class Order(string Id);",
    )];
    assert!(!cache.is_up_to_date(&fewer_inputs));
}

#[test]
fn test_lsp_initialize_and_capabilities() {
    let mut server = LspServer::new();
    let init_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("1".to_string()),
        method: Some("initialize".to_string()),
        params: Some(r#"{"rootUri":"file:///workspace"}"#.to_string()),
        result: None,
        error: None,
    };

    let responses = server.handle_message(&init_req);
    assert_eq!(responses.len(), 1);

    let resp = &responses[0];
    assert_eq!(resp.id.as_deref(), Some("1"));
    let res = resp.result.as_deref().expect("Expected initialize result");

    assert!(res.contains("\"hoverProvider\": true"));
    assert!(res.contains("\"definitionProvider\": true"));
    assert!(res.contains("\"completionProvider\":"));
    assert!(res.contains("\"name\": \"rsharpc-lsp\""));
}

#[test]
fn test_lsp_did_open_and_realtime_diagnostic_publication() {
    let mut server = LspServer::new();

    // Open a document containing RSHARP001 (service class field mutation outside constructor)
    let bad_source = r#"namespace Security;

service class KeyVault {
    string activeKey;

    public KeyVault(string initialKey) {
        this.activeKey = initialKey;
    }

    public void RotateKey(string newKey) {
        this.activeKey = newKey;
    }
}
"#;

    let did_open_params = format!(
        r#"{{"textDocument":{{"uri":"file:///KeyVault.rsharp","languageId":"rustsharp","version":1,"text":"{}"}}}}"#,
        bad_source.replace('\n', "\\n").replace('"', "\\\"")
    );

    let did_open_msg = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: None,
        method: Some("textDocument/didOpen".to_string()),
        params: Some(did_open_params),
        result: None,
        error: None,
    };

    let notifications = server.handle_message(&did_open_msg);
    assert_eq!(notifications.len(), 1);

    let notif = &notifications[0];
    assert_eq!(
        notif.method.as_deref(),
        Some("textDocument/publishDiagnostics")
    );
    let params = notif.params.as_deref().expect("Expected diagnostic params");

    assert!(params.contains("RSHARP001"));
    assert!(params.contains("\"severity\":1"));
    assert!(params.contains("Cannot mutate field 'activeKey' inside service class 'KeyVault'"));
}

#[test]
fn test_lsp_hover_displays_inferred_borrow_and_signature() {
    let mut server = LspServer::new();

    let source = r#"namespace Commerce;

record struct OrderItem(string Name, decimal Price);

class Order {
    decimal total;

    public void AddItem(OrderItem item) {
        this.total = this.total + item.Price;
    }
}
"#;

    // First open document
    let open_params = format!(
        r#"{{"textDocument":{{"uri":"file:///Order.rsharp","languageId":"rustsharp","version":1,"text":"{}"}}}}"#,
        source.replace('\n', "\\n").replace('"', "\\\"")
    );
    server.handle_message(&JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: None,
        method: Some("textDocument/didOpen".to_string()),
        params: Some(open_params),
        result: None,
        error: None,
    });

    // Request hover over 'AddItem' (line 7, col 18)
    let hover_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("42".to_string()),
        method: Some("textDocument/hover".to_string()),
        params: Some(r#"{"textDocument":{"uri":"file:///Order.rsharp"},"position":{"line":7,"character":18}}"#.to_string()),
        result: None,
        error: None,
    };

    let responses = server.handle_message(&hover_req);
    assert_eq!(responses.len(), 1);

    let resp = &responses[0];
    assert_eq!(resp.id.as_deref(), Some("42"));
    let result = resp.result.as_deref().expect("Expected hover result");

    // Must show inferred receiver borrow (&mut self) and lowered Rust signature
    assert!(result.contains("&mut self"));
    assert!(result.contains("pub fn add_item(&mut self, item: OrderItem) -> void"));
    assert!(result.contains("whole-program mutation analysis"));
}

#[test]
fn test_lsp_definition_jumps_to_symbol_declaration() {
    let mut server = LspServer::new();

    let source = r#"namespace Banking;

record class Account(string Id, decimal Balance);

class Bank {
    public Account FindAccount(string id) {
        return new Account(id, 100);
    }
}
"#;

    let open_params = format!(
        r#"{{"textDocument":{{"uri":"file:///Bank.rsharp","languageId":"rustsharp","version":1,"text":"{}"}}}}"#,
        source.replace('\n', "\\n").replace('"', "\\\"")
    );
    server.handle_message(&JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: None,
        method: Some("textDocument/didOpen".to_string()),
        params: Some(open_params),
        result: None,
        error: None,
    });

    // Request definition of 'Account' return type on line 5, col 14
    let def_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("101".to_string()),
        method: Some("textDocument/definition".to_string()),
        params: Some(r#"{"textDocument":{"uri":"file:///Bank.rsharp"},"position":{"line":5,"character":14}}"#.to_string()),
        result: None,
        error: None,
    };

    let responses = server.handle_message(&def_req);
    assert_eq!(responses.len(), 1);

    let resp = &responses[0];
    let result = resp.result.as_deref().expect("Expected definition result");

    // Must return the declaration range on line 2 (0-indexed: line 2)
    assert!(result.contains("\"uri\":\"file:///Bank.rsharp\""));
    assert!(result.contains("\"start\":{\"line\":2,"));
}

#[test]
fn test_lsp_completion_linq_and_keywords() {
    let mut server = LspServer::new();

    let source = r#"namespace Analytics;

class Query {
    public void Run() {
        var items = new List<int>();
        items.
    }
}
"#;

    let open_params = format!(
        r#"{{"textDocument":{{"uri":"file:///Query.rsharp","languageId":"rustsharp","version":1,"text":"{}"}}}}"#,
        source.replace('\n', "\\n").replace('"', "\\\"")
    );
    server.handle_message(&JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: None,
        method: Some("textDocument/didOpen".to_string()),
        params: Some(open_params),
        result: None,
        error: None,
    });

    // 1. Dot completion after 'items.' (line 5, character 14)
    let dot_comp_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("201".to_string()),
        method: Some("textDocument/completion".to_string()),
        params: Some(r#"{"textDocument":{"uri":"file:///Query.rsharp"},"position":{"line":5,"character":14}}"#.to_string()),
        result: None,
        error: None,
    };

    let responses = server.handle_message(&dot_comp_req);
    assert_eq!(responses.len(), 1);
    let result = responses[0]
        .result
        .as_deref()
        .expect("Expected completion result");

    assert!(result.contains("\"label\":\"Select\""));
    assert!(result.contains("\"label\":\"Where\""));
    assert!(result.contains("\"label\":\"OrderBy\""));
    assert!(result.contains("\"label\":\"ToList\""));

    // 2. Keyword completion at beginning of line (line 6, character 4)
    let kw_comp_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("202".to_string()),
        method: Some("textDocument/completion".to_string()),
        params: Some(r#"{"textDocument":{"uri":"file:///Query.rsharp"},"position":{"line":6,"character":4}}"#.to_string()),
        result: None,
        error: None,
    };

    let responses = server.handle_message(&kw_comp_req);
    assert_eq!(responses.len(), 1);
    let result = responses[0]
        .result
        .as_deref()
        .expect("Expected completion result");

    assert!(result.contains("\"label\":\"class\""));
    assert!(result.contains("\"label\":\"record\""));
    assert!(result.contains("\"label\":\"async\""));
    assert!(result.contains("\"label\":\"throws\""));
}

#[test]
fn test_lsp_cross_file_definition_and_workspace_symbols() {
    let mut server = LspServer::new();

    // 1. Initialize with workspace root
    let init_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("1".to_string()),
        method: Some("initialize".to_string()),
        params: Some(r#"{"rootUri":"file:///workspace"}"#.to_string()),
        result: None,
        error: None,
    };
    server.handle_message(&init_req);

    // 2. Open Models/Order.rsharp
    let order_source = r#"namespace Commerce.Models;

public record struct OrderItem(string Name, decimal Price);

public record class Order(string Id, List<OrderItem> Items) {
    public decimal CalculateTotal() {
        return 100;
    }
}
"#;
    let open_order = format!(
        r#"{{"textDocument":{{"uri":"file:///workspace/Models/Order.rsharp","languageId":"rustsharp","version":1,"text":"{}"}}}}"#,
        order_source.replace('\n', "\\n").replace('"', "\\\"")
    );
    server.handle_message(&JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: None,
        method: Some("textDocument/didOpen".to_string()),
        params: Some(open_order),
        result: None,
        error: None,
    });

    // 3. Open Services/Checkout.rsharp referencing types from Order.rsharp
    let checkout_source = r#"namespace Commerce.Services;
using Commerce.Models;

public class CheckoutService {
    public Order ProcessCheckout(string orderId) {
        var item = new OrderItem("Widget", 25);
        return new Order(orderId, new List<OrderItem>());
    }
}
"#;
    let open_checkout = format!(
        r#"{{"textDocument":{{"uri":"file:///workspace/Services/Checkout.rsharp","languageId":"rustsharp","version":1,"text":"{}"}}}}"#,
        checkout_source.replace('\n', "\\n").replace('"', "\\\"")
    );
    server.handle_message(&JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: None,
        method: Some("textDocument/didOpen".to_string()),
        params: Some(open_checkout),
        result: None,
        error: None,
    });

    // 4. Request cross-file Go to Definition of 'Order' from Checkout.rsharp (line 4, col 12)
    let def_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("301".to_string()),
        method: Some("textDocument/definition".to_string()),
        params: Some(r#"{"textDocument":{"uri":"file:///workspace/Services/Checkout.rsharp"},"position":{"line":4,"character":12}}"#.to_string()),
        result: None,
        error: None,
    };
    let def_resp = server.handle_message(&def_req);
    assert_eq!(def_resp.len(), 1);
    let def_res = def_resp[0].result.as_deref().expect("Expected definition");

    // Must point to Models/Order.rsharp
    assert!(def_res.contains("Models/Order.rsharp"));
    assert!(def_res.contains("\"start\":{\"line\":4,"));

    // 5. Request cross-file Go to Definition of 'OrderItem' from Checkout.rsharp (line 5, col 26)
    let item_def_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("302".to_string()),
        method: Some("textDocument/definition".to_string()),
        params: Some(r#"{"textDocument":{"uri":"file:///workspace/Services/Checkout.rsharp"},"position":{"line":5,"character":26}}"#.to_string()),
        result: None,
        error: None,
    };
    let item_def_resp = server.handle_message(&item_def_req);
    assert_eq!(item_def_resp.len(), 1);
    let item_res = item_def_resp[0]
        .result
        .as_deref()
        .expect("Expected definition");
    assert!(item_res.contains("Models/Order.rsharp"));
    assert!(item_res.contains("\"start\":{\"line\":2,"));

    // 6. Request Document Symbols (Outline) for Services/Checkout.rsharp
    let doc_sym_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("303".to_string()),
        method: Some("textDocument/documentSymbol".to_string()),
        params: Some(
            r#"{"textDocument":{"uri":"file:///workspace/Services/Checkout.rsharp"}}"#.to_string(),
        ),
        result: None,
        error: None,
    };
    let doc_sym_resp = server.handle_message(&doc_sym_req);
    assert_eq!(doc_sym_resp.len(), 1);
    let sym_res = doc_sym_resp[0].result.as_deref().expect("Expected symbols");
    assert!(sym_res.contains("\"name\":\"CheckoutService\""));
    assert!(sym_res.contains("\"name\":\"ProcessCheckout\""));

    // 7. Request Workspace Symbols for 'Order'
    let ws_sym_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("304".to_string()),
        method: Some("workspace/symbol".to_string()),
        params: Some(r#"{"query":"Order"}"#.to_string()),
        result: None,
        error: None,
    };
    let ws_sym_resp = server.handle_message(&ws_sym_req);
    assert_eq!(ws_sym_resp.len(), 1);
    let ws_res = ws_sym_resp[0]
        .result
        .as_deref()
        .expect("Expected ws symbols");
    assert!(ws_res.contains("\"name\":\"Order\""));
    assert!(ws_res.contains("\"name\":\"OrderItem\""));
}

#[test]
fn test_lsp_definition_colocated_rs_and_filesystem_fallback() {
    let mut server = LspServer::new();
    let abs_path =
        std::fs::canonicalize("examples/09_native_interop_crypto/src/CryptoService.rsharp")
            .expect("Canonicalize CryptoService.rsharp");
    let uri = format!("file://{}", abs_path.to_string_lossy());

    // Query definition of MurmurHash3 on line 10, col 35 without calling didOpen first
    let def_req = JsonRpcMessage {
        jsonrpc: "2.0".to_string(),
        id: Some("999".to_string()),
        method: Some("textDocument/definition".to_string()),
        params: Some(format!(
            r#"{{"textDocument":{{"uri":"{}"}},"position":{{"line":10,"character":35}}}}"#,
            uri
        )),
        result: None,
        error: None,
    };

    let responses = server.handle_message(&def_req);
    assert_eq!(responses.len(), 1);
    let result = responses[0]
        .result
        .as_deref()
        .expect("Expected definition result");

    // Must jump to NativeCrypto.rs or NativeCrypto.rsharp
    assert!(
        result.contains("NativeCrypto.rs") || result.contains("NativeCrypto.rsharp"),
        "Expected jump to NativeCrypto, got: {}",
        result
    );
}
