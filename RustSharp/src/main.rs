use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use rsharpc::compile_rsproj;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        print_usage();
        return ExitCode::from(1);
    }

    let subcommand = args[1].as_str();

    if subcommand == "lsp" {
        if let Err(e) = rsharpc::lsp::run_stdio_server() {
            eprintln!("rsharpc lsp error: {}", e);
            return ExitCode::from(1);
        }
        return ExitCode::SUCCESS;
    }

    if args.len() < 3 {
        print_usage();
        return ExitCode::from(1);
    }

    let rsproj_path = Path::new(&args[2]);

    // Locate ambient `stdlib/` directory relative to the current working directory if present
    let default_stdlib = PathBuf::from("stdlib");
    let stdlib_dir = if default_stdlib.exists() {
        Some(default_stdlib.as_path())
    } else {
        None
    };

    match subcommand {
        "watch" => {
            let mut watcher = rsharpc::project::WorkspaceWatcher::new(rsproj_path, stdlib_dir);
            watcher.watch_loop(true);
        }

        "check" => match compile_rsproj(rsproj_path, stdlib_dir, false) {
            Ok((cfg, synth, _diag)) => {
                println!(
                    "rsharpc check succeeded for '{}' ({} Rust modules verified, zero ownership errors).",
                    cfg.name,
                    synth.emitted_modules.len()
                );
                ExitCode::SUCCESS
            }
            Err(err_msg) => {
                eprintln!("{}", err_msg);
                ExitCode::from(1)
            }
        },

        "emit-rs" => match compile_rsproj(rsproj_path, stdlib_dir, true) {
            Ok((cfg, synth, _diag)) => {
                println!(
                    "Synthesized Cargo crate '{}' at {}",
                    cfg.name,
                    cfg.out_cargo_dir.display()
                );
                for rel_mod in synth.emitted_modules.keys() {
                    println!("  -> {}", rel_mod);
                }
                ExitCode::SUCCESS
            }
            Err(err_msg) => {
                eprintln!("{}", err_msg);
                ExitCode::from(1)
            }
        },

        "build" => match compile_rsproj(rsproj_path, stdlib_dir, true) {
            Ok((cfg, _synth, _diag)) => {
                println!(
                    "Synthesized Cargo workspace at {}. Running `cargo check`...",
                    cfg.out_cargo_dir.display()
                );
                let status = Command::new("cargo")
                    .arg("check")
                    .current_dir(&cfg.out_cargo_dir)
                    .status();

                match status {
                    Ok(s) if s.success() => {
                        println!("rsharpc build succeeded.");
                        ExitCode::SUCCESS
                    }
                    Ok(s) => {
                        eprintln!("cargo check exited with status: {}", s);
                        ExitCode::from(1)
                    }
                    Err(e) => {
                        eprintln!("Failed to invoke cargo: {}", e);
                        ExitCode::from(1)
                    }
                }
            }
            Err(err_msg) => {
                eprintln!("{}", err_msg);
                ExitCode::from(1)
            }
        },

        "run" => match compile_rsproj(rsproj_path, stdlib_dir, true) {
            Ok((cfg, _synth, _diag)) => {
                let main_rs = cfg.out_cargo_dir.join("src").join("main.rs");
                let status = if main_rs.exists() {
                    Command::new("cargo")
                        .arg("run")
                        .arg("--quiet")
                        .current_dir(&cfg.out_cargo_dir)
                        .status()
                } else {
                    println!(
                        "Synthesized library crate '{}' at {}. Running `cargo test`...",
                        cfg.name,
                        cfg.out_cargo_dir.display()
                    );
                    Command::new("cargo")
                        .arg("test")
                        .arg("--quiet")
                        .arg("--")
                        .arg("--nocapture")
                        .current_dir(&cfg.out_cargo_dir)
                        .status()
                };

                match status {
                    Ok(s) if s.success() => ExitCode::SUCCESS,
                    Ok(s) => {
                        eprintln!("cargo run/test exited with status: {}", s);
                        ExitCode::from(1)
                    }
                    Err(e) => {
                        eprintln!("Failed to invoke cargo: {}", e);
                        ExitCode::from(1)
                    }
                }
            }
            Err(err_msg) => {
                eprintln!("{}", err_msg);
                ExitCode::from(1)
            }
        },

        "bindgen" => {
            let mut out_file: Option<PathBuf> = None;
            let mut namespace: Option<String> = None;
            let mut crate_name: Option<String> = None;

            let mut i = 3;
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
                    _ => {}
                }
                i += 1;
            }

            match rsharpc::bindgen::generate_crate_header(
                rsproj_path,
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
                    eprintln!("rsharpc bindgen error: {}", err);
                    ExitCode::from(1)
                }
            }
        }

        other => {
            eprintln!("Unknown subcommand '{}'.", other);
            print_usage();
            ExitCode::from(1)
        }
    }
}

fn print_usage() {
    eprintln!("RustSharp Compiler Prototype (rsharpc)");
    eprintln!("Usage:");
    eprintln!("  rsharpc check <path/to/Project.rsproj>    Run Pass 1, Pass 2 & Pass 2.5 pre-flight checks");
    eprintln!("  rsharpc emit-rs <path/to/Project.rsproj>  Emit synthesized Cargo workspace & .rsharp.map files");
    eprintln!("  rsharpc build <path/to/Project.rsproj>    Synthesize Cargo workspace and run cargo check");
    eprintln!("  rsharpc run <path/to/Project.rsproj>      Synthesize Cargo workspace and run cargo run / cargo test");
    eprintln!("  rsharpc bindgen <path/to/crate-or-rs>     Generate .d.rsharp ambient header from native Rust crate");
    eprintln!("  rsharpc watch <path/to/Project.rsproj>    Continuous file watcher triggering incremental builds");
    eprintln!("  rsharpc lsp                              Start pure-Rust JSON-RPC 2.0 Language Server on stdio");
}
