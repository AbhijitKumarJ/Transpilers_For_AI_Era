use std::path::Path;

use rsharpc::compile_rsproj;

#[test]
fn test_end_to_end_commerce_workspace_rust_emission_and_cargo_synthesis() {
    let rsproj_path = Path::new("tests/fixtures/commerce_workspace/Commerce.rsproj");
    let stdlib_dir = Path::new("stdlib");

    let (cfg, synth, diag) = compile_rsproj(rsproj_path, Some(stdlib_dir), false)
        .expect("Expected commerce_workspace to compile cleanly through Pass 1, Pass 2, Pass 2.5, and Pass 3");

    assert!(!diag.has_errors());
    assert_eq!(cfg.name, "commerce_workspace");

    // 1. Verify synthesized Cargo.toml
    assert!(synth
        .cargo_toml_content
        .contains("name = \"commerce_workspace\""));
    assert!(synth.cargo_toml_content.contains("rust_decimal = \"1.36\""));

    // 2. Verify synthesized src/lib.rs virtual namespace module tree
    assert!(synth.lib_rs_content.contains("pub mod commerce {"));
    assert!(synth.lib_rs_content.contains("pub mod checkout;"));
    assert!(synth.lib_rs_content.contains("pub mod ingest;"));
    assert!(synth.lib_rs_content.contains("pub mod payments;"));

    // 3. Verify emitted Rust for `src/commerce/checkout.rs` (`OrderHandler.rsharp`)
    let checkout_rs = synth
        .emitted_modules
        .get("src/commerce/checkout.rs")
        .expect("Missing src/commerce/checkout.rs");

    // - Service dependency `_tax` wrapped in `Arc<TaxCalculator>`
    assert!(
        checkout_rs.contains("tax: Arc<TaxCalculator>,"),
        "Expected Arc<TaxCalculator> field in OrderHandler:\n{}",
        checkout_rs
    );
    // - Bottom-up interprocedural mutation inference on `checkout` (`order: &mut Order, coupon: &str`)
    //   and `throws ValidationError` rewritten to `-> Result<(), ValidationError>`
    assert!(
        checkout_rs.contains(
            "pub fn checkout(&self, order: &mut Order, coupon: &str) -> Result<(), ValidationError>"
        ),
        "Expected inferred signature on checkout:\n{}",
        checkout_rs
    );
    // - Decimal literal `0.0m` lowered to `Decimal::new(0, 1)` and `throw new ValidationError(...)` lowered to `return Err(...)`
    assert!(checkout_rs.contains("if order.total <= Decimal::new(0, 1)"));
    assert!(checkout_rs.contains(
        "return Err(ValidationError { reason: \"Order total must be positive\".to_string() });"
    ));
    // - Re-borrowing `&*order` after mutable call `self.apply_coupon(order, coupon);`
    assert!(checkout_rs.contains("self.apply_coupon(order, coupon);"));
    assert!(checkout_rs.contains("self.tax.record_audit(&*order);"));
    assert!(checkout_rs.contains("Ok(())"));

    // 4. Verify emitted Rust for `src/commerce/payments.rs` (`PaymentHierarchy.rsharp`)
    let payments_rs = synth
        .emitted_modules
        .get("src/commerce/payments.rs")
        .expect("Missing src/commerce/payments.rs");

    // - Closed-world base struct `PaymentBase`, flattened `pub base: PaymentBase`, `Deref`, and tagged union `pub enum Payment`
    assert!(payments_rs.contains("pub struct PaymentBase {"));
    assert!(payments_rs.contains("pub base: PaymentBase,"));
    assert!(payments_rs.contains("impl std::ops::Deref for CardPayment"));
    assert!(payments_rs.contains("pub enum Payment {"));
    assert!(payments_rs.contains("Card(CardPayment),"));
    assert!(payments_rs.contains("Crypto(CryptoPayment),"));
    assert!(payments_rs.contains("Payment::Card(inner) => inner.summarize()"));

    // 5. Verify co-located `PacketHeader.rs` linked into `src/commerce/ingest.rs`
    let ingest_rs = synth
        .emitted_modules
        .get("src/commerce/ingest.rs")
        .expect("Missing src/commerce/ingest.rs");

    assert!(ingest_rs.contains("#[derive(Clone, Copy, Debug, PartialEq)]"));
    assert!(ingest_rs.contains("pub struct PacketHeader {"));
    assert!(ingest_rs.contains("pub mod packet_header_ext;"));
    assert!(synth
        .emitted_modules
        .contains_key("src/commerce/packet_header_ext.rs"));

    // 6. Verify bidirectional `.rsharp.map` source map generation and `rustc` span translation
    let checkout_map = synth
        .sourcemaps
        .get("src/commerce/checkout.rs")
        .expect("Missing sourcemap for checkout.rs");
    assert!(!checkout_map.entries.is_empty());

    let fake_rustc_err = "error[E0308]: mismatched types\n  --> src/commerce/checkout.rs:25:9\n";
    let translated = checkout_map.translate_rustc_stderr(fake_rustc_err);
    assert!(
        translated.contains("Features/Checkout/OrderHandler.rsharp:"),
        "Expected rustc stderr translator to map back to OrderHandler.rsharp, got:\n{}",
        translated
    );
}
