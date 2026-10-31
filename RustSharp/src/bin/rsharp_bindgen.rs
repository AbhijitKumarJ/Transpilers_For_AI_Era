//! `rsharp-bindgen` CLI tool: generates ambient `.d.rsharp` headers from Cargo crates.

use std::env;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use rsharpc::bindgen::generate_crate_header;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 || args[1] == "--help" || args[1] == "-h" {
        print_usage();
        return ExitCode::from(if args.len() < 2 { 1 } else { 0 });
    }

    let input_path = Path::new(&args[1]);
    let mut out_file: Option<PathBuf> = None;
    let mut namespace: Option<String> = None;
    let mut crate_name: Option<String> = None;

    let mut i = 2;
    while i < args.len() {
        match args[i].as_str() {
            "--out" | "-o" if i + 1 < args.len() => {
                out_file = Some(PathBuf::from(&args[i + 1]));
                i += 1;
            }
            "--namespace" | "-n" if i + 1 < args.len() => {
                namespace = Some(args[i + 1].clone());
                i += 1;
            }
            "--crate-name" | "-c" if i + 1 < args.len() => {
                crate_name = Some(args[i + 1].clone());
                i += 1;
            }
            other => {
                eprintln!("Unknown argument '{}'.", other);
                print_usage();
                return ExitCode::from(1);
            }
        }
        i += 1;
    }

    match generate_crate_header(
        input_path,
        namespace.as_deref(),
        crate_name.as_deref(),
        out_file.as_deref(),
    ) {
        Ok(header) => {
            if let Some(out_p) = out_file {
                println!(
                    "Successfully generated ambient header at: {}",
                    out_p.display()
                );
            } else {
                println!("{}", header);
            }
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("rsharp-bindgen error: {}", err);
            ExitCode::from(1)
        }
    }
}

fn print_usage() {
    eprintln!("rsharp-bindgen: Cargo Crate to RustSharp (.d.rsharp) Ambient Header Generator");
    eprintln!("Usage:");
    eprintln!("  rsharp-bindgen <path/to/crate-dir-or-lib.rs> [OPTIONS]");
    eprintln!();
    eprintln!("Options:");
    eprintln!(
        "  -o, --out <path>         Target output file path (e.g. stubs/SampleCrypto.d.rsharp)"
    );
    eprintln!(
        "  -n, --namespace <name>   Target C# namespace (defaults to PascalCase of crate name)"
    );
    eprintln!("  -c, --crate-name <name>  Override crate name (defaults to Cargo.toml name)");
    eprintln!("  -h, --help               Display this help message");
}
