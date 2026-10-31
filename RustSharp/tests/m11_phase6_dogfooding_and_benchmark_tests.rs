//! Phase 6 Test Suite: Real-World Dogfooding, Ported Ecosystem Libraries & Benchmark Harness.

use std::path::Path;
use std::time::Instant;

use rsharpc::compile_rsproj;

#[test]
fn test_dogfooding_all_8_ported_libraries_compile_cleanly() {
    let stdlib_dir = Path::new("stdlib");

    let library_projects = [
        ("Slugify", "examples/01_slugify/Slugify.rsproj"),
        ("Levenshtein", "examples/02_levenshtein/Levenshtein.rsproj"),
        (
            "CryptoSha256",
            "examples/03_crypto_sha256/CryptoSha256.rsproj",
        ),
        ("BigInteger", "examples/04_big_integer/BigInteger.rsproj"),
        ("JsonParser", "examples/05_json_parser/JsonParser.rsproj"),
        (
            "JsonSerializer",
            "examples/06_json_serializer/JsonSerializer.rsproj",
        ),
        ("HttpClient", "examples/07_http_client/HttpClient.rsproj"),
        ("RestService", "examples/08_rest_service/RestService.rsproj"),
    ];

    for (name, rsproj_path) in library_projects {
        let path = Path::new(rsproj_path);
        let res = compile_rsproj(path, Some(stdlib_dir), false);
        assert!(
            res.is_ok(),
            "Ported library '{}' failed compilation: {:?}",
            name,
            res.err()
        );

        let (cfg, synth, diag) = res.unwrap();
        assert!(
            !diag.has_errors(),
            "Ported library '{}' reported errors: {}",
            name,
            diag.format_all()
        );
        assert!(
            !synth.emitted_modules.is_empty(),
            "Ported library '{}' produced no emitted modules.",
            name
        );
        assert!(
            !synth.cargo_toml_content.is_empty(),
            "Ported library '{}' produced empty Cargo.toml.",
            name
        );
        println!(
            "[Dogfooding] '{}' ({}) -> {} modules generated cleanly.",
            name,
            cfg.name,
            synth.emitted_modules.len()
        );
    }
}

#[test]
fn test_dogfooding_mixed_rs_and_rsharp_projects_compile_cleanly() {
    let stdlib_dir = Path::new("stdlib");

    let mixed_projects = [
        (
            "CryptoProject",
            "examples/09_native_interop_crypto/CryptoProject.rsproj",
        ),
        (
            "PhysicsEngine",
            "examples/10_game_physics_engine/PhysicsEngine.rsproj",
        ),
        (
            "DatabaseLayer",
            "examples/11_mixed_database_layer/DatabaseLayer.rsproj",
        ),
    ];

    for (name, rsproj_path) in mixed_projects {
        let path = Path::new(rsproj_path);
        let res = compile_rsproj(path, Some(stdlib_dir), false);
        assert!(
            res.is_ok(),
            "Mixed project '{}' failed compilation: {:?}",
            name,
            res.err()
        );

        let (cfg, synth, diag) = res.unwrap();
        assert!(
            !diag.has_errors(),
            "Mixed project '{}' reported errors: {}",
            name,
            diag.format_all()
        );
        assert!(
            !synth.emitted_modules.is_empty(),
            "Mixed project '{}' produced no emitted modules.",
            name
        );
        assert!(
            !synth.linked_colocated_files.is_empty(),
            "Mixed project '{}' expected linked co-located .rs files.",
            name
        );
        println!(
            "[Dogfooding Mixed] '{}' ({}) -> {} modules, {} co-located .rs files linked.",
            name,
            cfg.name,
            synth.emitted_modules.len(),
            synth.linked_colocated_files.len()
        );
    }
}

#[test]
fn test_benchmark_compiler_throughput_lines_per_second() {
    // Generate a large synthetic corpus of 100 classes with methods and LINQ pipelines
    let mut large_corpus = String::from("namespace BenchmarkSuite;\n\n");
    let num_classes = 100;
    for c in 0..num_classes {
        large_corpus.push_str(&format!(
            r#"
public record struct Item{c}(int Id, decimal Price);

public class Processor{c} {{
    decimal total;

    public void Add(Item{c} item) {{
        this.total = this.total + item.Price;
    }}

    public List<int> FilterIds(List<Item{c}> items) {{
        return items.Where(x => x.Id > 10).Select(x => x.Id).ToList();
    }}
}}
"#,
            c = c
        ));
    }

    let line_count = large_corpus.lines().count();
    let files = [("Benchmark.rsharp", large_corpus.as_str())];

    let start = Instant::now();
    let (units, symtab, diag) = rsharpc::analyze_workspace_with_preflight(&files);
    let elapsed = start.elapsed();

    assert!(
        !diag.has_errors(),
        "Benchmark corpus failed semantic checks"
    );
    assert_eq!(units.len(), 1);
    assert_eq!(units[0].types.len(), num_classes * 2);

    let secs = elapsed.as_secs_f64();
    let lines_per_sec = (line_count as f64) / secs;

    println!(
        "\n[Benchmark Throughput] Processed {} lines in {:.4}s -> {:.0} lines/sec (symtab types: {}).",
        line_count,
        secs,
        lines_per_sec,
        symtab.types.len()
    );

    // Assert compiler achieves high throughput (>10,000 lines/sec on debug build)
    assert!(
        lines_per_sec > 10_000.0,
        "Compiler throughput too low: {:.0} lines/sec",
        lines_per_sec
    );
}

#[test]
fn test_dogfooding_functional_correctness_and_clean_synthesis() {
    let stdlib_dir = Path::new("stdlib");

    // 1. Verify Levenshtein distance library synthesis
    let (_cfg, synth, _) = compile_rsproj(
        Path::new("examples/02_levenshtein/Levenshtein.rsproj"),
        Some(stdlib_dir),
        false,
    )
    .expect("Levenshtein compilation failed");

    let rs_code = synth
        .emitted_modules
        .get("src/text_algorithms.rs")
        .expect("Missing text_algorithms.rs");
    assert!(rs_code.contains("pub fn compute_distance(source: &str, target: &str) -> i32"));
    assert!(rs_code.contains("v1[(j + 1) as usize] = (min_cost).min(substitution_cost);"));

    // 2. Verify Sha256 library synthesis
    let (_cfg2, synth2, _) = compile_rsproj(
        Path::new("examples/03_crypto_sha256/CryptoSha256.rsproj"),
        Some(stdlib_dir),
        false,
    )
    .expect("CryptoSha256 compilation failed");

    let rs_code2 = synth2
        .emitted_modules
        .get("src/cryptography.rs")
        .expect("Missing cryptography.rs");
    assert!(rs_code2.contains("pub fn rotate_right(value: u32, bits: i32) -> u32"));
    assert!(rs_code2.contains("pub fn ch(x: u32, y: u32, z: u32) -> u32"));
    assert!(rs_code2.contains("pub fn maj(x: u32, y: u32, z: u32) -> u32"));

    // 3. Verify RestService Axum library synthesis
    let (_cfg3, synth3, _) = compile_rsproj(
        Path::new("examples/08_rest_service/RestService.rsproj"),
        Some(stdlib_dir),
        false,
    )
    .expect("RestService compilation failed");

    let rs_code3 = synth3
        .emitted_modules
        .get("src/api_service.rs")
        .expect("Missing api_service.rs");
    assert!(rs_code3.contains("#[axum::routing::get(\"/users/:id\")]"));
    assert!(rs_code3.contains("#[axum::routing::post(\"/users\")]"));
}
