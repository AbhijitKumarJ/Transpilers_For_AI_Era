Here are the complete, raw individual source files for **Milestone 6 (Pass 3: Bidirectional SourceMap, Idiomatic Rust Expression & AST Emitter, Co-Located `.rs` Linker & Cargo Workspace Synthesizer, CLI Entry Point, `stdlib/RustSharp.Core.d.rsharp`, Multi-File `commerce_workspace` Fixtures, End-to-End Verification Suite, and `README.md`)** of the **RustSharp Prototype Transpiler (`rsharpc`)**.

---

### `stdlib/RustSharp.Core.d.rsharp`

```csharp
// ============================================================================
// FILE: stdlib/RustSharp.Core.d.rsharp
// Ambient Standard Library — Zero Runtime Overhead, 100% Compile-Time Erasure
// ============================================================================

namespace RustSharp.Core;

extern using std::vec::Vec;
extern using std::collections::HashMap;
extern using std::collections::HashSet as RustHashSet;
extern using std::time::Duration as RustDuration;
extern using rust_decimal::Decimal as RustDecimal;

// ----------------------------------------------------------------------------
// 1. COMPILER INTRINSIC ATTRIBUTES
// ----------------------------------------------------------------------------

public abstract class Attribute { }

public sealed class MapsToAttribute : Attribute
{
    public MapsToAttribute(string rustTarget) { }
}

public sealed class ParamTypeAttribute : Attribute
{
    public ParamTypeAttribute(string borrowedRustType) { }
}

public sealed class InlineTemplateAttribute : Attribute
{
    public InlineTemplateAttribute(string rustTemplate) { }
}

public sealed class BorrowsAttribute : Attribute { }
public sealed class MutatesAttribute : Attribute { }
public sealed class MovesAttribute : Attribute { }

public sealed class LinqStageAttribute : Attribute
{
    public LinqStageAttribute(string stageKind) { }
}

// ----------------------------------------------------------------------------
// 2. CORE TRAIT CONTRACTS & DETERMINISTIC RAII (IDisposable -> Drop)
// ----------------------------------------------------------------------------

[MapsTo("std::ops::Drop")]
public extensible interface IDisposable
{
    [Mutates]
    [MapsTo("drop")]
    void Dispose();
}

[MapsTo("std::cmp::PartialEq")]
public extensible interface IEquatable<T>
{
    [Borrows]
    [MapsTo("eq")]
    bool Equals([Borrows] T other);
}

[MapsTo("std::cmp::Ord")]
public extensible interface IComparable<T>
{
    [Borrows]
    [InlineTemplate("{self}.cmp(&{0})")]
    int CompareTo([Borrows] T other);
}

// ----------------------------------------------------------------------------
// 3. STRINGS & SLICES (string -> String / &str, ReadOnlySpan<T> -> &[T])
// ----------------------------------------------------------------------------

[MapsTo("std::string::String")]
[ParamType("&str")]
public primitive class String
{
    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Length { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Borrows]
    [InlineTemplate("{self}.contains({0})")]
    public extern bool Contains([Borrows] string value);

    [Borrows]
    [InlineTemplate("{self}.starts_with({0})")]
    public extern bool StartsWith([Borrows] string prefix);

    [Borrows]
    [InlineTemplate("{self}.ends_with({0})")]
    public extern bool EndsWith([Borrows] string suffix);

    [Borrows]
    [MapsTo("to_lowercase")]
    public extern string ToLower();

    [Borrows]
    [MapsTo("to_uppercase")]
    public extern string ToUpper();

    [Borrows]
    [InlineTemplate("{self}.trim().to_string()")]
    public extern string Trim();

    [Borrows]
    [InlineTemplate("{self}.as_bytes()")]
    public extern ReadOnlySpan<byte> AsBytes();

    [Borrows]
    [InlineTemplate("{self}.split({0}).map(|s| s.to_string()).collect::<Vec<String>>()")]
    public extern List<string> Split([Borrows] string delimiter);
}

[MapsTo("&[{T}]")]
public primitive struct ReadOnlySpan<T>
{
    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Length { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Borrows]
    [InlineTemplate("{self}[{0} as usize]")]
    public extern T this[int index] { get; }

    [Borrows]
    [InlineTemplate("&{self}[({0} as usize)..({1} as usize)]")]
    public extern ReadOnlySpan<T> Slice(int start, int length);
}

[MapsTo("&mut [{T}]")]
public primitive struct Span<T>
{
    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Length { get; }

    [Mutates]
    [InlineTemplate("{self}[{0} as usize]")]
    public extern T this[int index] { get; set; }

    [Mutates]
    [MapsTo("fill")]
    public extern void Fill(T value);
}

// ----------------------------------------------------------------------------
// 4. COLLECTIONS: List<T> (-> Vec<T>), Dictionary<K,V>, HashSet<T>
// ----------------------------------------------------------------------------

[MapsTo("std::vec::Vec")]
[ParamType("&[{T}]")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("Vec::new()")]
    public extern List();

    [InlineTemplate("Vec::with_capacity({0} as usize)")]
    public extern List(int capacity);

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Mutates]
    [MapsTo("push")]
    public extern void Add([Moves] T item);

    [Mutates]
    [InlineTemplate("{self}.extend({0})")]
    public extern void AddRange([Moves] IEnumerable<T> items);

    [Mutates]
    [InlineTemplate("{self}.insert({0} as usize, {1})")]
    public extern void Insert(int index, [Moves] T item);

    [Mutates]
    [InlineTemplate("{self}.remove({0} as usize)")]
    public extern T RemoveAt(int index);

    [Mutates]
    [MapsTo("pop")]
    public extern T? Pop();

    [Mutates]
    [MapsTo("clear")]
    public extern void Clear();

    [Borrows]
    [InlineTemplate("{self}.contains(&{0})")]
    public extern bool Contains([Borrows] T item);

    [Borrows]
    [InlineTemplate("{self}.as_slice()")]
    public extern ReadOnlySpan<T> AsSpan();

    [Mutates]
    [InlineTemplate("{self}.as_mut_slice()")]
    public extern Span<T> AsMutSpan();

    [Mutates]
    [MapsTo("sort")]
    public extern void Sort();

    [Borrows]
    [InlineTemplate("{self}[{0} as usize]")]
    public extern T this[int index] { [Borrows] get; [Mutates] set; }
}

[MapsTo("std::collections::HashMap")]
public primitive class Dictionary<TKey, TValue> : IEnumerable<KeyValuePair<TKey, TValue>>
{
    [InlineTemplate("std::collections::HashMap::new()")]
    public extern Dictionary();

    [InlineTemplate("std::collections::HashMap::with_capacity({0} as usize)")]
    public extern Dictionary(int capacity);

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Mutates]
    [InlineTemplate("{self}.insert({0}, {1})")]
    public extern void Add([Moves] TKey key, [Moves] TValue value);

    [Borrows]
    [InlineTemplate("{self}.get(&{0}).cloned()")]
    public extern TValue? GetOrDefault([Borrows] TKey key);

    [Borrows]
    [InlineTemplate("{self}.contains_key(&{0})")]
    public extern bool ContainsKey([Borrows] TKey key);

    [Mutates]
    [InlineTemplate("{self}.remove(&{0}).is_some()")]
    public extern bool Remove([Borrows] TKey key);

    [Mutates]
    [MapsTo("clear")]
    public extern void Clear();

    [InlineTemplate("{self}[&{0}]")]
    public extern TValue this[[Borrows] TKey key]
    {
        [Borrows] get;
        [Mutates] [InlineTemplate("{self}.insert({0}, {value})")] set;
    }
}

[MapsTo("std::collections::HashSet")]
public primitive class HashSet<T> : IEnumerable<T>
{
    [InlineTemplate("std::collections::HashSet::new()")]
    public extern HashSet();

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Mutates]
    [MapsTo("insert")]
    public extern bool Add([Moves] T item);

    [Borrows]
    [InlineTemplate("{self}.contains(&{0})")]
    public extern bool Contains([Borrows] T item);

    [Mutates]
    [InlineTemplate("{self}.remove(&{0})")]
    public extern bool Remove([Borrows] T item);
}

[MapsTo("({TKey}, {TValue})")]
public primitive struct KeyValuePair<TKey, TValue>
{
    [InlineTemplate("{self}.0")]
    public extern TKey Key { get; }

    [InlineTemplate("{self}.1")]
    public extern TValue Value { get; }
}

// ----------------------------------------------------------------------------
// 5. OPTION, RESULT, AND CONCURRENCY PRIMITIVES
// ----------------------------------------------------------------------------

[MapsTo("std::option::Option")]
public primitive struct Option<T>
{
    [Borrows]
    [MapsTo("is_some")]
    public extern bool HasValue { get; }

    [Borrows]
    [MapsTo("is_none")]
    public extern bool IsNull { get; }

    [Moves]
    [MapsTo("unwrap")]
    public extern T Value();

    [Moves]
    [MapsTo("unwrap_or")]
    public extern T GetValueOrDefault([Moves] T defaultValue);
}

[MapsTo("std::sync::Arc<std::sync::RwLock<{T}>>")]
public primitive class SharedState<T>
{
    [InlineTemplate("std::sync::Arc::new(std::sync::RwLock::new({0}))")]
    public extern SharedState([Moves] T initialValue);

    [Borrows]
    [InlineTemplate("{self}.read().unwrap()")]
    public extern T Read();

    [Borrows]
    [InlineTemplate("{self}.write().unwrap()")]
    public extern T Write();
}

// ----------------------------------------------------------------------------
// 6. ZERO-COST LINQ PIPELINE DECLARATIONS (IEnumerable<T> -> Iterator)
// ----------------------------------------------------------------------------

[MapsTo("impl std::iter::Iterator<Item = {T}>")]
public primitive interface IEnumerable<T>
{
    [LinqStage("Filter")]
    [InlineTemplate("{self}.filter({0})")]
    IEnumerable<T> Where(Func<T, bool> predicate);

    [LinqStage("Map")]
    [InlineTemplate("{self}.map({0})")]
    IEnumerable<TResult> Select<TResult>(Func<T, TResult> selector);

    [LinqStage("FlatMap")]
    [InlineTemplate("{self}.flat_map({0})")]
    IEnumerable<TResult> SelectMany<TResult>(Func<T, IEnumerable<TResult>> selector);

    [LinqStage("Take")]
    [InlineTemplate("{self}.take({0} as usize)")]
    IEnumerable<T> Take(int count);

    [LinqStage("Skip")]
    [InlineTemplate("{self}.skip({0} as usize)")]
    IEnumerable<T> Skip(int count);

    [LinqStage("Enumerate")]
    [InlineTemplate("{self}.enumerate()")]
    IEnumerable<KeyValuePair<int, T>> WithIndex();

    [LinqStage("TerminalCollectVec")]
    [InlineTemplate("{self}.collect::<Vec<_>>()")]
    List<T> ToList();

    [LinqStage("TerminalCollectSet")]
    [InlineTemplate("{self}.collect::<std::collections::HashSet<_>>()")]
    HashSet<T> ToHashSet();

    [LinqStage("TerminalAny")]
    [InlineTemplate("{self}.any({0})")]
    bool Any(Func<T, bool> predicate);

    [LinqStage("TerminalAll")]
    [InlineTemplate("{self}.all({0})")]
    bool All(Func<T, bool> predicate);

    [LinqStage("TerminalFirstOrDefault")]
    [InlineTemplate("{self}.next()")]
    T? FirstOrDefault();

    [LinqStage("TerminalFind")]
    [InlineTemplate("{self}.find({0})")]
    T? FirstOrDefault(Func<T, bool> predicate);

    [LinqStage("TerminalCount")]
    [InlineTemplate("{self}.count() as i32")]
    int Count();

    [LinqStage("TerminalSum")]
    [InlineTemplate("{self}.sum()")]
    T Sum();
}

// ----------------------------------------------------------------------------
// 7. SYSTEM CONSOLE & TIME FACADES
// ----------------------------------------------------------------------------

public static primitive class Console
{
    [InlineTemplate("println!(\"{}\", {0})")]
    public static extern void WriteLine([Borrows] string message);

    [InlineTemplate("print!(\"{}\", {0})")]
    public static extern void Write([Borrows] string message);

    [InlineTemplate("eprintln!(\"{}\", {0})")]
    public static extern void WriteErrorLine([Borrows] string message);
}

[MapsTo("std::time::Duration")]
public primitive struct TimeSpan
{
    [InlineTemplate("std::time::Duration::from_millis({0} as u64)")]
    public static extern TimeSpan FromMilliseconds(long ms);

    [InlineTemplate("std::time::Duration::from_secs({0} as u64)")]
    public static extern TimeSpan FromSeconds(long seconds);

    [Borrows]
    [InlineTemplate("{self}.as_millis() as i64")]
    public extern long TotalMilliseconds { get; }
}

```

---

### `src/codegen/sourcemap.rs`

```rust
use crate::diagnostics::SourceSpan;

/// Single bidirectional line mapping between an emitted `.rs` module line
/// and its originating `.rsharp` source file, line, and column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceMapEntry {
    pub rs_file: String,
    pub rs_line: u32,
    pub rsharp_file: String,
    pub rsharp_line: u32,
    pub rsharp_col: u32,
}

/// Tracks bidirectional `.rs` <-> `.rsharp` source line mappings for a synthesized Rust module
/// and translates `rustc` fallback diagnostics back into original `.rsharp` coordinates.
#[derive(Clone, Debug, Default)]
pub struct RustSourceMap {
    pub rs_file: String,
    pub entries: Vec<SourceMapEntry>,
}

impl RustSourceMap {
    pub fn new(rs_file: impl Into<String>) -> Self {
        Self {
            rs_file: rs_file.into(),
            entries: Vec::new(),
        }
    }

    pub fn record(&mut self, rs_line: u32, span: &SourceSpan) {
        if span.filename.is_empty() || span.start_line == 0 {
            return;
        }
        self.entries.push(SourceMapEntry {
            rs_file: self.rs_file.clone(),
            rs_line,
            rsharp_file: span.filename.clone(),
            rsharp_line: span.start_line,
            rsharp_col: span.start_col,
        });
    }

    /// Resolves an emitted `.rs` line number back to the closest originating `.rsharp` location.
    pub fn lookup_rsharp_location(&self, rs_line: u32) -> Option<&SourceMapEntry> {
        self.entries
            .iter()
            .rev()
            .find(|e| e.rs_line <= rs_line)
            .or_else(|| self.entries.first())
    }

    /// Serializes the source map to a deterministic `.rsharp.map` text table.
    pub fn to_map_file_string(&self) -> String {
        let mut out = String::from("# RustSharp Bidirectional Source Map (.rsharp.map)\n");
        out.push_str("# rs_file:rs_line => rsharp_file:rsharp_line:rsharp_col\n");
        for entry in &self.entries {
            out.push_str(&format!(
                "{}:{} => {}:{}:{}\n",
                entry.rs_file,
                entry.rs_line,
                entry.rsharp_file,
                entry.rsharp_line,
                entry.rsharp_col
            ));
        }
        out
    }

    /// Rewrites `--> src/module.rs:line:col` spans in raw `rustc` output to point directly
    /// to the originating `.rsharp` file and line.
    pub fn translate_rustc_stderr(&self, stderr: &str) -> String {
        let mut translated = Vec::new();
        let needle = format!("--> {}:", self.rs_file);

        for line in stderr.lines() {
            let trimmed = line.trim_start();
            if let Some(rest) = trimmed.strip_prefix(&needle) {
                let mut parts = rest.split(':');
                if let Some(line_str) = parts.next() {
                    if let Ok(rs_line) = line_str.parse::<u32>() {
                        if let Some(mapped) = self.lookup_rsharp_location(rs_line) {
                            translated.push(format!(
                                "  --> {}:{}:{} (mapped from {}:{})",
                                mapped.rsharp_file,
                                mapped.rsharp_line,
                                mapped.rsharp_col,
                                self.rs_file,
                                rs_line
                            ));
                            continue;
                        }
                    }
                }
            }
            translated.push(line.to_string());
        }

        translated.join("\n")
    }
}

```

---

### `src/codegen/expr_emitter.rs`

```rust
use std::collections::{HashMap, HashSet};

use crate::codegen::sourcemap::RustSourceMap;
use crate::frontend::ast::{
    AssignOp, BinaryOp, Block, BorrowMode, CallerArgCoercion, Expr, ExprKind, FieldStorageMode,
    LambdaBody, LinqChain, LinqOp, LinqTerminal, LiteralValue, Pattern, PrimitiveLowering, Stmt,
    SymbolId, TypeRef, UnaryOp,
};
use crate::frontend::tokens::InterpPart;
use crate::semantics::primitive_resolver::format_rust_owned_type;
use crate::semantics::symbols::{pascal_to_snake_case, GlobalSymbolTable};

/// Pass 3 Idiomatic Rust Statement & Expression Emitter.
///
/// Lowers decorated `.rsharp` statements and expressions into zero-cost Rust syntax:
/// - Applies caller argument coercions (`&`, `&mut`, `&*`, `.clone()`, `Arc::clone(&...)`).
/// - Expands `[InlineTemplate("...")]` and `[MapsTo("...")]` primitive operations.
/// - Emits fused `.iter().filter(...).map(...).collect()` pipelines from `ExprKind::LinqChain`.
/// - Emits `Result<T, E>` propagation (`?`), `Ok(...)` / `Err(...)` wrapping, and `try / catch` `match` blocks.
/// - Lowers `10.0m` decimal literals to `Decimal::new(mantissa, scale)` and `..` slices to `&buf[a..b]`.
pub struct RustExprEmitter<'a> {
    pub symtab: &'a GlobalSymbolTable,
    pub current_type_id: Option<SymbolId>,
    pub type_fields: HashMap<String, FieldStorageMode>,
    pub base_struct_fields: HashSet<String>,
    pub method_param_borrows: HashMap<String, BorrowMode>,
    pub is_fallible_method: bool,
    pub is_void_return: bool,
}

impl<'a> RustExprEmitter<'a> {
    pub fn new(symtab: &'a GlobalSymbolTable, current_type_id: Option<SymbolId>) -> Self {
        let mut type_fields = HashMap::new();
        let mut base_struct_fields = HashSet::new();

        if let Some(tid) = current_type_id {
            if let Some(tsym) = symtab.types.get(&tid) {
                for &fid in &tsym.fields {
                    if let Some(f) = symtab.fields.get(&fid) {
                        type_fields.insert(f.name.clone(), f.storage_mode);
                    }
                }
                for &pid in &tsym.properties {
                    if let Some(p) = symtab.properties.get(&pid) {
                        type_fields.insert(p.name.clone(), p.storage_mode);
                    }
                }
                for &base_id in &tsym.resolved_base_type_ids {
                    if let Some(bsym) = symtab.types.get(&base_id) {
                        for &bfid in &bsym.fields {
                            if let Some(bf) = symtab.fields.get(&bfid) {
                                base_struct_fields.insert(bf.name.clone());
                            }
                        }
                        for &bpid in &bsym.properties {
                            if let Some(bp) = symtab.properties.get(&bpid) {
                                base_struct_fields.insert(bp.name.clone());
                            }
                        }
                    }
                }
            }
        }

        Self {
            symtab,
            current_type_id,
            type_fields,
            base_struct_fields,
            method_param_borrows: HashMap::new(),
            is_fallible_method: false,
            is_void_return: true,
        }
    }

    pub fn emit_block(
        &mut self,
        block: &Block,
        indent: usize,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        let mut lines = Vec::new();
        let len = block.stmts.len();

        for (idx, stmt) in block.stmts.iter().enumerate() {
            let is_last = idx + 1 == len;
            let rendered = self.emit_stmt(stmt, indent, is_last, sourcemap, current_rs_line);
            if !rendered.is_empty() {
                lines.push(rendered);
            }
        }

        // If the method is `Fallible` (`throws TError`) and returns `void` (`Result<(), E>`),
        // append the trailing `Ok(())` if the block doesn't already end with an explicit return/throw.
        if self.is_fallible_method && self.is_void_return {
            let ends_with_terminator = block
                .stmts
                .last()
                .map(|s| matches!(s, Stmt::Return { .. } | Stmt::Throw { .. }))
                .unwrap_or(false);
            if !ends_with_terminator {
                let pad = "    ".repeat(indent);
                lines.push(format!("{}Ok(())", pad));
                *current_rs_line += 1;
            }
        }

        lines.join("\n")
    }

    pub fn emit_stmt(
        &mut self,
        stmt: &Stmt,
        indent: usize,
        is_last_in_block: bool,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        let pad = "    ".repeat(indent);

        match stmt {
            Stmt::Block(b) => {
                let mut out = format!("{}{{\n", pad);
                *current_rs_line += 1;
                let inner = self.emit_block(b, indent + 1, sourcemap, current_rs_line);
                if !inner.is_empty() {
                    out.push_str(&inner);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));
                *current_rs_line += 1;
                out
            }

            Stmt::LocalVar {
                span,
                name,
                explicit_type,
                init,
                inferred_mut,
                ..
            } => {
                sourcemap.record(*current_rs_line, span);
                let var_snake = normalize_local_ident(name);
                let mut_kw = if *inferred_mut { "mut " } else { "" };

                let type_annot = if let Some(ty) = explicit_type {
                    if matches!(init.kind, ExprKind::RangeSlice { .. })
                        && ty.short_name() == "ReadOnlySpan"
                    {
                        format!(": {}", format_rust_owned_type(ty, self.symtab))
                    } else {
                        format!(": {}", format_rust_owned_type(ty, self.symtab))
                    }
                } else {
                    String::new()
                };

                let rhs = self.emit_expr(init);
                *current_rs_line += 1;
                format!("{}let {}{}{}= {};", pad, mut_kw, var_snake, type_annot, rhs)
            }

            Stmt::UsingResource {
                span,
                name,
                explicit_type,
                init,
                inferred_mut,
                ..
            } => {
                sourcemap.record(*current_rs_line, span);
                let var_snake = normalize_local_ident(name);
                let mut_kw = if *inferred_mut { "mut " } else { "" };
                let type_annot = explicit_type
                    .as_ref()
                    .map(|ty| format!(": {}", format_rust_owned_type(ty, self.symtab)))
                    .unwrap_or_default();
                let rhs = self.emit_expr(init);
                *current_rs_line += 1;
                format!(
                    "{}let {}{}{}= {}; // RAII Drop at scope exit",
                    pad, mut_kw, var_snake, type_annot, rhs
                )
            }

            Stmt::If {
                span,
                cond,
                then_branch,
                else_branch,
            } => {
                sourcemap.record(*current_rs_line, span);
                let cond_str = self.emit_expr(cond);
                let mut out = format!("{}if {} {{\n", pad, cond_str);
                *current_rs_line += 1;

                let then_body = self.emit_branch_contents(then_branch, indent + 1, sourcemap, current_rs_line);
                if !then_body.is_empty() {
                    out.push_str(&then_body);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));

                if let Some(el) = else_branch {
                    out.push_str(" else {\n");
                    *current_rs_line += 1;
                    let else_body =
                        self.emit_branch_contents(el, indent + 1, sourcemap, current_rs_line);
                    if !else_body.is_empty() {
                        out.push_str(&else_body);
                        out.push('\n');
                    }
                    out.push_str(&format!("{}}}", pad));
                }

                *current_rs_line += 1;
                out
            }

            Stmt::While { span, cond, body } => {
                sourcemap.record(*current_rs_line, span);
                let cond_str = self.emit_expr(cond);
                let mut out = format!("{}while {} {{\n", pad, cond_str);
                *current_rs_line += 1;
                let inner = self.emit_branch_contents(body, indent + 1, sourcemap, current_rs_line);
                if !inner.is_empty() {
                    out.push_str(&inner);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));
                *current_rs_line += 1;
                out
            }

            Stmt::ForEach {
                span,
                item_name,
                collection,
                body,
                iter_borrow_mode,
                ..
            } => {
                sourcemap.record(*current_rs_line, span);
                let item_snake = normalize_local_ident(item_name);
                let coll_str = self.emit_expr(collection);
                let iter_method = match iter_borrow_mode {
                    BorrowMode::MutBorrow => "iter_mut()",
                    BorrowMode::OwnedMove => "into_iter()",
                    _ => "iter()",
                };
                let mut out = format!("{}for {} in {}.{} {{\n", pad, item_snake, coll_str, iter_method);
                *current_rs_line += 1;
                let inner = self.emit_branch_contents(body, indent + 1, sourcemap, current_rs_line);
                if !inner.is_empty() {
                    out.push_str(&inner);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));
                *current_rs_line += 1;
                out
            }

            Stmt::Return { span, value } => {
                sourcemap.record(*current_rs_line, span);
                *current_rs_line += 1;
                match value {
                    Some(v) => {
                        let rendered = self.emit_expr(v);
                        if self.is_fallible_method {
                            if is_last_in_block {
                                format!("{}Ok({})", pad, rendered)
                            } else {
                                format!("{}return Ok({});", pad, rendered)
                            }
                        } else if is_last_in_block {
                            format!("{}{}", pad, rendered)
                        } else {
                            format!("{}return {};", pad, rendered)
                        }
                    }
                    None => {
                        if self.is_fallible_method {
                            format!("{}return Ok(());", pad)
                        } else {
                            format!("{}return;", pad)
                        }
                    }
                }
            }

            Stmt::Throw { span, error_expr } => {
                sourcemap.record(*current_rs_line, span);
                let err_rendered = self.emit_expr(error_expr);
                *current_rs_line += 1;
                format!("{}return Err({});", pad, err_rendered)
            }

            Stmt::TryCatch {
                span,
                try_block,
                catches,
            } => {
                sourcemap.record(*current_rs_line, span);
                self.emit_try_catch_match(try_block, catches, indent, sourcemap, current_rs_line)
            }

            Stmt::ExprStmt { span, expr } => {
                sourcemap.record(*current_rs_line, span);
                let rendered = self.emit_expr(expr);
                *current_rs_line += 1;
                format!("{}{};", pad, rendered)
            }
        }
    }

    fn emit_branch_contents(
        &mut self,
        branch: &Stmt,
        indent: usize,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        match branch {
            Stmt::Block(b) => {
                let saved_fallible = self.is_fallible_method;
                let saved_void = self.is_void_return;
                self.is_void_return = false; // prevent implicit `Ok(())` inside nested `if/while/for` blocks
                let out = self.emit_block(b, indent, sourcemap, current_rs_line);
                self.is_fallible_method = saved_fallible;
                self.is_void_return = saved_void;
                out
            }
            single => self.emit_stmt(single, indent, false, sourcemap, current_rs_line),
        }
    }

    fn emit_try_catch_match(
        &mut self,
        try_block: &Block,
        catches: &[crate::frontend::ast::CatchArm],
        indent: usize,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        let pad = "    ".repeat(indent);
        let arm_pad = "    ".repeat(indent + 1);

        // Single-statement `try { return FallibleCall(...); } catch (E err) { ... }`
        let scrutinee_str = if try_block.stmts.len() == 1 {
            match &try_block.stmts[0] {
                Stmt::Return { value: Some(expr), .. } | Stmt::ExprStmt { expr, .. } => {
                    self.emit_expr(expr)
                }
                _ => "(() -> Result<_, _> { Ok(()) })()".to_string(),
            }
        } else {
            "(() -> Result<_, _> { Ok(()) })()".to_string()
        };

        let mut out = format!("{}match {} {{\n", pad, scrutinee_str);
        *current_rs_line += 1;
        out.push_str(&format!("{}Ok(_val) => _val,\n", arm_pad));
        *current_rs_line += 1;

        if let Some(first_catch) = catches.first() {
            let err_var = first_catch
                .var_name
                .as_deref()
                .map(normalize_local_ident)
                .unwrap_or_else(|| "_err".to_string());

            if first_catch.body.stmts.len() == 1 {
                if let Stmt::Return { value: Some(v), .. } = &first_catch.body.stmts[0] {
                    let catch_expr = self.emit_expr(v);
                    out.push_str(&format!("{}Err({}) => {},\n", arm_pad, err_var, catch_expr));
                    *current_rs_line += 1;
                } else {
                    out.push_str(&format!("{}Err({}) => {{\n", arm_pad, err_var));
                    *current_rs_line += 1;
                    let inner = self.emit_block(
                        &first_catch.body,
                        indent + 2,
                        sourcemap,
                        current_rs_line,
                    );
                    out.push_str(&inner);
                    out.push_str(&format!("\n{}}}\n", arm_pad));
                    *current_rs_line += 1;
                }
            } else {
                out.push_str(&format!("{}Err({}) => {{\n", arm_pad, err_var));
                *current_rs_line += 1;
                let inner =
                    self.emit_block(&first_catch.body, indent + 2, sourcemap, current_rs_line);
                out.push_str(&inner);
                out.push_str(&format!("\n{}}}\n", arm_pad));
                *current_rs_line += 1;
            }
        } else {
            out.push_str(&format!("{}Err(_err) => Default::default(),\n", arm_pad));
            *current_rs_line += 1;
        }

        out.push_str(&format!("{}}}", pad));
        *current_rs_line += 1;
        out
    }

    pub fn emit_expr(&mut self, expr: &Expr) -> String {
        let core = self.emit_expr_core(expr);
        if expr.append_try_question_mark {
            format!("{}?", core)
        } else {
            core
        }
    }

    fn emit_expr_core(&mut self, expr: &Expr) -> String {
        match &expr.kind {
            ExprKind::Literal(lit) => match lit {
                LiteralValue::Int(v) => v.to_string(),
                LiteralValue::Float(v) => {
                    let s = v.to_string();
                    if s.contains('.') {
                        s
                    } else {
                        format!("{}.0", s)
                    }
                }
                LiteralValue::Decimal(raw) => format_decimal_literal(raw),
                LiteralValue::String(s) => format!("\"{}\"", escape_rust_string(s)),
                LiteralValue::Char(c) => format!("'{}'", c),
                LiteralValue::Bool(b) => b.to_string(),
                LiteralValue::Null => "None".to_string(),
            },

            ExprKind::InterpolatedString(parts) => {
                let mut fmt_str = String::new();
                let mut fmt_args = Vec::new();
                for part in parts {
                    match part {
                        InterpPart::Literal(lit) => {
                            fmt_str.push_str(&escape_rust_string(lit));
                        }
                        InterpPart::ExprSource(src) => {
                            fmt_str.push_str("{}");
                            fmt_args.push(self.translate_interp_expr(src));
                        }
                    }
                }
                if fmt_args.is_empty() {
                    format!("\"{}\".to_string()", fmt_str)
                } else {
                    format!("format!(\"{}\", {})", fmt_str, fmt_args.join(", "))
                }
            }

            ExprKind::Identifier { name, .. } => {
                if self.type_fields.contains_key(name) {
                    format!("self.{}", normalize_field_ident(name))
                } else if self.base_struct_fields.contains(name) {
                    format!("self.base.{}", normalize_field_ident(name))
                } else {
                    normalize_local_ident(name)
                }
            }

            ExprKind::This => "self".to_string(),
            ExprKind::Base => "self.base".to_string(),

            ExprKind::Unary { op, operand } => {
                let inner = self.emit_expr(operand);
                match op {
                    UnaryOp::Not => format!("!{}", inner),
                    UnaryOp::Neg => format!("-{}", inner),
                    UnaryOp::Await => format!("{}.await", inner),
                    UnaryOp::FromEnd => inner,
                }
            }

            ExprKind::Binary { op, left, right } => {
                let l = self.emit_expr(left);
                let r = self.emit_expr(right);
                let op_str = match op {
                    BinaryOp::Add => "+",
                    BinaryOp::Sub => "-",
                    BinaryOp::Mul => "*",
                    BinaryOp::Div => "/",
                    BinaryOp::Rem => "%",
                    BinaryOp::Eq => "==",
                    BinaryOp::Neq => "!=",
                    BinaryOp::Lt => "<",
                    BinaryOp::Gt => ">",
                    BinaryOp::Lte => "<=",
                    BinaryOp::Gte => ">=",
                    BinaryOp::And => "&&",
                    BinaryOp::Or => "||",
                };
                format!("{} {} {}", l, op_str, r)
            }

            ExprKind::Assignment { op, target, value } => {
                let lhs = self.emit_expr(target);
                let rhs = self.emit_expr(value);
                match op {
                    AssignOp::Assign => format!("{} = {}", lhs, rhs),
                    AssignOp::AddAssign => format!("{} += {}", lhs, rhs),
                    AssignOp::SubAssign => format!("{} -= {}", lhs, rhs),
                    AssignOp::MulAssign => format!("{} *= {}", lhs, rhs),
                    AssignOp::DivAssign => format!("{} /= {}", lhs, rhs),
                    AssignOp::NullCoalesceEq => format!("{}.get_or_insert({})", lhs, rhs),
                }
            }

            ExprKind::NullCoalesce { left, right } => {
                let l = self.emit_expr(left);
                let r = self.emit_expr(right);
                format!("{}.unwrap_or({})", l, r)
            }

            ExprKind::IsPattern { expr: inner, pattern } => {
                let scrutinee = self.emit_expr(inner);
                let pat_str = self.emit_pattern(pattern);
                format!("matches!({}, {})", scrutinee, pat_str)
            }

            ExprKind::MemberAccess {
                target,
                member,
                is_null_conditional,
                ..
            } => {
                if matches!(target.kind, ExprKind::This) {
                    if self.base_struct_fields.contains(member) {
                        return format!("self.base.{}", normalize_field_ident(member));
                    }
                    return format!("self.{}", normalize_field_ident(member));
                }

                let recv_str = self.emit_expr(target);
                if *is_null_conditional {
                    return format!(
                        "{}.as_ref().map(|_x| &_x.{})",
                        recv_str,
                        normalize_field_ident(member)
                    );
                }

                // Built-in property templates on `String`, `List`, `ReadOnlySpan`, `Span`
                match member.as_str() {
                    "Length" | "Count" => format!("{}.len() as i32", recv_str),
                    "IsEmpty" => format!("{}.is_empty()", recv_str),
                    _ => format!("{}.{}", recv_str, normalize_field_ident(member)),
                }
            }

            ExprKind::MethodCall {
                receiver,
                method_name,
                args,
                resolved_overload,
                primitive_lowering,
                ..
            } => {
                let recv_str = receiver
                    .as_ref()
                    .map(|r| self.emit_expr(r))
                    .unwrap_or_else(|| "self".to_string());

                let rendered_args: Vec<String> = args
                    .iter()
                    .map(|a| {
                        let raw_arg = self.emit_expr(&a.expr);
                        self.apply_caller_coercion(&a.expr, raw_arg, a.expr.caller_coercion)
                    })
                    .collect();

                // 1. Check `primitive_lowering` (`[InlineTemplate]` or `[MapsTo]`)
                match primitive_lowering {
                    PrimitiveLowering::InlineTemplate { template } => {
                        return expand_primitive_inline_template(template, &recv_str, &rendered_args);
                    }
                    PrimitiveLowering::DirectSymbol { rust_path } => {
                        return format!("{}({})", format!("{}.{}", recv_str, rust_path), rendered_args.join(", "));
                    }
                    PrimitiveLowering::OperatorIndex => {
                        if let Some(first) = rendered_args.first() {
                            return format!("{}[{} as usize]", recv_str, first);
                        }
                    }
                    PrimitiveLowering::None => {}
                }

                // 2. Resolve disambiguated Rust method name from `GlobalSymbolTable`
                let rust_fn_name = resolved_overload
                    .and_then(|mid| self.symtab.methods.get(&mid))
                    .map(|m| m.disambiguated_rust_name.clone())
                    .filter(|s| !s.is_empty())
                    .unwrap_or_else(|| pascal_to_snake_case(method_name));

                let is_static_call = resolved_overload
                    .and_then(|mid| self.symtab.methods.get(&mid))
                    .map(|m| m.is_static)
                    .unwrap_or(false);

                if let Some(recv) = receiver {
                    if let ExprKind::Identifier { name, .. } = &recv.kind {
                        if is_static_call || self.symtab.short_name_index.contains_key(name) {
                            return format!("{}::{}({})", name, rust_fn_name, rendered_args.join(", "));
                        }
                    }
                    format!("{}.{}({})", recv_str, rust_fn_name, rendered_args.join(", "))
                } else if is_static_call {
                    format!("Self::{}({})", rust_fn_name, rendered_args.join(", "))
                } else {
                    format!("self.{}({})", rust_fn_name, rendered_args.join(", "))
                }
            }

            ExprKind::IndexAccess { target, indices } => {
                let t = self.emit_expr(target);
                let idx_strs: Vec<String> = indices
                    .iter()
                    .map(|i| format!("{} as usize", self.emit_expr(&i.expr)))
                    .collect();
                format!("{}[{}]", t, idx_strs.join(", "))
            }

            ExprKind::RangeSlice { target, start, end } => {
                let s = start
                    .as_ref()
                    .map(|e| self.emit_expr(e))
                    .unwrap_or_default();
                let e = end
                    .as_ref()
                    .map(|e| self.emit_expr(e))
                    .unwrap_or_default();
                if let Some(t) = target {
                    let t_str = self.emit_expr(t);
                    format!("&{}[{}..{}]", t_str, s, e)
                } else {
                    format!("{}..{}", s, e)
                }
            }

            ExprKind::Construct {
                ty,
                args,
                resolved_ctor,
                primitive_lowering,
            } => self.emit_construct_expr(ty, args, *resolved_ctor, primitive_lowering),

            ExprKind::Lambda { params, body } => {
                let param_list: Vec<String> = params.iter().map(|p| normalize_local_ident(p)).collect();
                let body_str = match body {
                    LambdaBody::Expr(e) => self.emit_expr(e),
                    LambdaBody::Block(b) => {
                        let mut dummy_map = RustSourceMap::default();
                        let mut dummy_line = 1;
                        format!("{{\n{}\n}}", self.emit_block(b, 1, &mut dummy_map, &mut dummy_line))
                    }
                };
                format!("|{}| {}", param_list.join(", "), body_str)
            }

            ExprKind::Switch { scrutinee, arms } => {
                let scrut_str = self.emit_expr(scrutinee);
                let mut rendered_arms = Vec::new();
                for arm in arms {
                    let pat = self.emit_pattern(&arm.pattern);
                    let guard = arm
                        .guard
                        .as_ref()
                        .map(|g| format!(" if {}", self.emit_expr(g)))
                        .unwrap_or_default();
                    let body = self.emit_expr(&arm.body);
                    rendered_arms.push(format!("{}{} => {}", pat, guard, body));
                }
                format!("match {} {{ {} }}", scrut_str, rendered_arms.join(", "))
            }

            ExprKind::LinqChain(chain) => self.emit_fused_linq_chain(chain),
        }
    }

    fn emit_construct_expr(
        &mut self,
        ty: &TypeRef,
        args: &[crate::frontend::ast::ArgNode],
        resolved_ctor: Option<SymbolId>,
        primitive_lowering: &PrimitiveLowering,
    ) -> String {
        let rendered_args: Vec<String> = args
            .iter()
            .map(|a| {
                let raw = self.emit_expr(&a.expr);
                if matches!(a.expr.kind, ExprKind::Literal(LiteralValue::String(_))) {
                    format!("{}.to_string()", raw)
                } else {
                    self.apply_caller_coercion(&a.expr, raw, a.expr.caller_coercion)
                }
            })
            .collect();

        if let PrimitiveLowering::InlineTemplate { template } = primitive_lowering {
            return expand_primitive_inline_template(template, "", &rendered_args);
        }

        match ty.short_name() {
            "List" => {
                if rendered_args.is_empty() {
                    return "Vec::new()".to_string();
                }
                return format!("Vec::with_capacity({} as usize)", rendered_args[0]);
            }
            "Dictionary" => {
                return "std::collections::HashMap::new()".to_string();
            }
            "HashSet" => {
                return "std::collections::HashSet::new()".to_string();
            }
            _ => {}
        }

        // Check if `ty` is a `Record` with primary constructor parameters -> emit struct literal `Order { id: ..., total: ... }`
        if let Some(candidates) = self.symtab.short_name_index.get(ty.short_name()) {
            for &cid in candidates {
                if let Some(tsym) = self.symtab.types.get(&cid) {
                    if matches!(tsym.kind, crate::frontend::ast::TypeKind::Record { .. })
                        && tsym.constructors.is_empty()
                        && tsym.fields.len() == rendered_args.len()
                    {
                        let mut field_inits = Vec::new();
                        for (i, &fid) in tsym.fields.iter().enumerate() {
                            if let Some(fsym) = self.symtab.fields.get(&fid) {
                                field_inits.push(format!(
                                    "{}: {}",
                                    normalize_field_ident(&fsym.name),
                                    rendered_args[i]
                                ));
                            }
                        }
                        return format!("{} {{ {} }}", ty.short_name(), field_inits.join(", "));
                    }
                }
            }
        }

        let ctor_name = resolved_ctor
            .and_then(|cid| self.symtab.methods.get(&cid))
            .map(|c| c.disambiguated_rust_name.clone())
            .filter(|n| !n.is_empty())
            .unwrap_or_else(|| "new".to_string());

        format!("{}::{}({})", ty.short_name(), ctor_name, rendered_args.join(", "))
    }

    pub fn apply_caller_coercion(
        &self,
        arg_expr: &Expr,
        rendered_expr: String,
        coercion: CallerArgCoercion,
    ) -> String {
        match coercion {
            CallerArgCoercion::None => rendered_expr,
            CallerArgCoercion::BorrowShared => {
                if matches!(
                    arg_expr.kind,
                    ExprKind::Literal(LiteralValue::String(_)) | ExprKind::RangeSlice { .. }
                ) {
                    return rendered_expr;
                }
                if let ExprKind::Identifier { name, .. } = &arg_expr.kind {
                    if let Some(&param_mode) = self.method_param_borrows.get(name) {
                        return match param_mode {
                            BorrowMode::ReadBorrow => rendered_expr,
                            BorrowMode::MutBorrow => format!("&*{}", rendered_expr),
                            _ => format!("&{}", rendered_expr),
                        };
                    }
                }
                format!("&{}", rendered_expr)
            }
            CallerArgCoercion::BorrowMutable => {
                if let ExprKind::Identifier { name, .. } = &arg_expr.kind {
                    if let Some(&param_mode) = self.method_param_borrows.get(name) {
                        if param_mode == BorrowMode::MutBorrow {
                            return rendered_expr;
                        }
                    }
                }
                format!("&mut {}", rendered_expr)
            }
            CallerArgCoercion::CloneOwned => format!("{}.clone()", rendered_expr),
            CallerArgCoercion::ArcClone => format!("Arc::clone(&{})", rendered_expr),
        }
    }

    fn emit_fused_linq_chain(&mut self, chain: &LinqChain) -> String {
        let src_str = self.emit_expr(&chain.source);
        let iter_init = if chain.consumes_source {
            format!("{}.into_iter()", src_str)
        } else {
            format!("{}.iter()", src_str)
        };

        let mut stages = vec![iter_init];
        for op in &chain.ops {
            match op {
                LinqOp::Where { predicate } => {
                    stages.push(format!("filter({})", self.emit_expr(predicate)));
                }
                LinqOp::Select { selector } => {
                    stages.push(format!("map({})", self.emit_expr(selector)));
                }
                LinqOp::SelectMany { selector } => {
                    stages.push(format!("flat_map({})", self.emit_expr(selector)));
                }
                LinqOp::Take { count } => {
                    stages.push(format!("take({} as usize)", self.emit_expr(count)));
                }
                LinqOp::Skip { count } => {
                    stages.push(format!("skip({} as usize)", self.emit_expr(count)));
                }
                LinqOp::WithIndex => {
                    stages.push("enumerate()".to_string());
                }
            }
        }

        let term_str = match &chain.terminal {
            LinqTerminal::ToList => "collect::<Vec<_>>()".to_string(),
            LinqTerminal::ToHashSet => "collect::<std::collections::HashSet<_>>()".to_string(),
            LinqTerminal::Any {
                predicate: Some(pred),
            } => format!("any({})", self.emit_expr(pred)),
            LinqTerminal::Any { predicate: None } => "next().is_some()".to_string(),
            LinqTerminal::All { predicate } => format!("all({})", self.emit_expr(predicate)),
            LinqTerminal::FirstOrDefault {
                predicate: Some(pred),
            } => format!("find({}).cloned()", self.emit_expr(pred)),
            LinqTerminal::FirstOrDefault { predicate: None } => "next().cloned()".to_string(),
            LinqTerminal::Count => "count() as i32".to_string(),
            LinqTerminal::Sum => "sum()".to_string(),
        };
        stages.push(term_str);

        stages.join(".")
    }

    fn emit_pattern(&mut self, pattern: &Pattern) -> String {
        match pattern {
            Pattern::Wildcard(_) => "_".to_string(),
            Pattern::Null(_) => "None".to_string(),
            Pattern::Literal(_, lit) => match lit {
                LiteralValue::Int(v) => v.to_string(),
                LiteralValue::String(s) => format!("\"{}\"", escape_rust_string(s)),
                LiteralValue::Bool(b) => b.to_string(),
                _ => "_".to_string(),
            },
            Pattern::TypePattern {
                ty,
                bind_name,
                property_patterns,
                ..
            } => {
                let type_name = ty.short_name();
                if !property_patterns.is_empty() {
                    let fields: Vec<String> = property_patterns
                        .iter()
                        .map(|pp| {
                            format!(
                                "{}: {}",
                                normalize_field_ident(&pp.field_name),
                                self.emit_pattern(&pp.pattern)
                            )
                        })
                        .collect();
                    format!("{} {{ {}, .. }}", type_name, fields.join(", "))
                } else if let Some(b) = bind_name {
                    format!("{}({})", type_name, normalize_local_ident(b))
                } else {
                    type_name.to_string()
                }
            }
        }
    }

    fn translate_interp_expr(&self, raw: &str) -> String {
        let trimmed = raw.trim();
        if self.type_fields.contains_key(trimmed) {
            format!("self.{}", normalize_field_ident(trimmed))
        } else if self.base_struct_fields.contains(trimmed) {
            format!("self.base.{}", normalize_field_ident(trimmed))
        } else if let Some((obj, prop)) = trimmed.split_once('.') {
            format!(
                "{}.{}",
                normalize_local_ident(obj.trim()),
                normalize_field_ident(prop.trim())
            )
        } else {
            normalize_local_ident(trimmed)
        }
    }
}

pub fn expand_primitive_inline_template(tpl: &str, receiver: &str, args: &[String]) -> String {
    let mut out = tpl.replace("{self}", receiver);
    for (i, arg) in args.iter().enumerate() {
        let placeholder = format!("{{{}}}", i);
        let addr_placeholder = format!("&{{{}}}", i);
        if out.contains(&addr_placeholder) && arg.starts_with('&') {
            out = out.replace(&addr_placeholder, arg);
        } else {
            out = out.replace(&placeholder, arg);
        }
    }
    out
}

/// Converts a C# decimal literal string (e.g. `"10.0"`, `"100.25"`) into `Decimal::new(mantissa, scale)`.
pub fn format_decimal_literal(raw: &str) -> String {
    if let Some((int_part, frac_part)) = raw.split_once('.') {
        let scale = frac_part.len() as u32;
        let combined = format!("{}{}", int_part, frac_part);
        let mantissa = combined.parse::<i64>().unwrap_or(0);
        format!("Decimal::new({}, {})", mantissa, scale)
    } else {
        let mantissa = raw.parse::<i64>().unwrap_or(0);
        format!("Decimal::new({}, 0)", mantissa)
    }
}

pub fn normalize_field_ident(name: &str) -> String {
    let stripped = name.trim_start_matches('_');
    if stripped.is_empty() {
        "_field".to_string()
    } else {
        pascal_to_snake_case(stripped)
    }
}

pub fn normalize_local_ident(name: &str) -> String {
    if name.starts_with('_') {
        let stripped = name.trim_start_matches('_');
        format!("_{}", pascal_to_snake_case(stripped))
    } else {
        pascal_to_snake_case(name)
    }
}

fn escape_rust_string(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

```

---

### `src/codegen/rs_ast_emitter.rs`

```rust
use std::collections::HashSet;

use crate::codegen::expr_emitter::{
    normalize_field_ident, normalize_local_ident, RustExprEmitter,
};
use crate::codegen::sourcemap::RustSourceMap;
use crate::frontend::ast::{
    AccessMod, BorrowMode, ConstructorDecl, EffectSignature, FieldStorageMode, MemberDecl,
    MethodDecl, PolymorphismStrategy, Stmt, SymbolId, TypeDecl, TypeKind,
};
use crate::semantics::primitive_resolver::{format_rust_owned_type, format_rust_param_type};
use crate::semantics::symbols::{pascal_to_snake_case, GlobalSymbolTable};

/// Pass 3 Idiomatic Rust Module & Archetype Emitter.
///
/// Emits formatted, idiomatic `.rs` module files from decorated `.rsharp` `TypeDecl` nodes:
/// - `record` / `struct` -> `#[derive(Clone, Debug, PartialEq)] pub struct ...`
/// - `service class` -> `Arc<T>` dependency fields + `&self` methods
/// - `shared class` -> `Arc<RwLock<T>>` fields
/// - `PolymorphismStrategy::ClosedWorldEnum` -> Base struct + exhaustive `pub enum` + `match` dispatch
/// - `PolymorphismStrategy::FlattenedSubStruct` -> `pub base: BaseStruct` + `impl Deref` / `impl DerefMut`
/// - `PolymorphismStrategy::OpenTrait` -> `pub trait ...`
/// - `IDisposable` (`has_disposable_drop`) -> `impl Drop for ... { fn drop(&mut self) { ... } }`
pub struct RustModuleEmitter<'a> {
    pub symtab: &'a GlobalSymbolTable,
}

impl<'a> RustModuleEmitter<'a> {
    pub fn new(symtab: &'a GlobalSymbolTable) -> Self {
        Self { symtab }
    }

    pub fn emit_namespace_module(
        &mut self,
        ns: &[String],
        types: &[&TypeDecl],
        rs_rel_path: &str,
    ) -> (String, RustSourceMap) {
        let mut sourcemap = RustSourceMap::new(rs_rel_path);
        let mut out = String::from("// Auto-generated by rsharpc — DO NOT EDIT\n");
        out.push_str("#![allow(dead_code, unused_variables, unused_imports, clippy::all)]\n\n");
        let mut current_line: u32 = 4;

        // Collect required crate/std imports based on archetypes and types used in this namespace
        let mut header_imports = Vec::new();
        if self.module_uses_arc(types) {
            header_imports.push("use std::sync::Arc;".to_string());
        }
        if self.module_uses_rwlock(types) {
            header_imports.push("use std::sync::RwLock;".to_string());
        }
        if self.module_uses_decimal(types) {
            header_imports.push("use rust_decimal::Decimal;".to_string());
        }

        if !header_imports.is_empty() {
            for imp in header_imports {
                out.push_str(&imp);
                out.push('\n');
                current_line += 1;
            }
            out.push('\n');
            current_line += 1;
        }

        // Track types emitted as part of a closed-world enum hierarchy so we don't duplicate them
        let mut emitted_ids = HashSet::new();

        for &decl in types {
            if emitted_ids.contains(&decl.id) {
                continue;
            }
            if matches!(decl.kind, TypeKind::PrimitiveClass { .. }) {
                continue;
            }

            // Check if `decl` is a closed-world base class/interface
            if let PolymorphismStrategy::ClosedWorldEnum { variants } = &decl.inferred_polymorphism
            {
                let variant_decls: Vec<&TypeDecl> = variants
                    .iter()
                    .filter_map(|vid| types.iter().copied().find(|t| t.id == *vid))
                    .collect();

                let rendered = self.emit_closed_world_enum_hierarchy(
                    decl,
                    &variant_decls,
                    &mut sourcemap,
                    &mut current_line,
                );
                out.push_str(&rendered);
                out.push('\n');
                current_line += 1;

                emitted_ids.insert(decl.id);
                for vd in variant_decls {
                    emitted_ids.insert(vd.id);
                }
                continue;
            }

            let rendered = match decl.kind {
                TypeKind::Interface { .. } => {
                    self.emit_open_trait(decl, &mut sourcemap, &mut current_line)
                }
                TypeKind::Enum => self.emit_enum_decl(decl, &mut sourcemap, &mut current_line),
                TypeKind::Record { .. } | TypeKind::ValueStruct => {
                    self.emit_record_or_struct(decl, &mut sourcemap, &mut current_line)
                }
                TypeKind::ServiceClass | TypeKind::SharedClass | TypeKind::StandardClass => {
                    self.emit_class_archetype(decl, &mut sourcemap, &mut current_line)
                }
                TypeKind::PrimitiveClass { .. } => String::new(),
            };

            if !rendered.is_empty() {
                out.push_str(&rendered);
                out.push('\n');
                current_line += 1;
            }
            emitted_ids.insert(decl.id);
        }

        let _ = ns;
        (out, sourcemap)
    }

    fn emit_record_or_struct(
        &mut self,
        decl: &TypeDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &decl.span);
        let vis = format_rust_visibility(decl.access);
        let mut out = String::new();

        let is_copy_struct = matches!(
            decl.kind,
            TypeKind::ValueStruct | TypeKind::Record { is_struct: true }
        );
        if is_copy_struct {
            out.push_str("#[derive(Clone, Copy, Debug, PartialEq)]\n");
        } else {
            out.push_str("#[derive(Clone, Debug, PartialEq)]\n");
        }
        *current_line += 1;

        let generics = format_type_params(&decl.type_params);
        out.push_str(&format!("{}struct {}{} {{\n", vis, decl.name, generics));
        *current_line += 1;

        // Primary constructor parameters (for `record Order(int Id, decimal Total);`)
        for p in &decl.primary_ctor_params {
            let f_name = normalize_field_ident(&p.name);
            let f_ty = format_rust_owned_type(&p.ty, self.symtab);
            out.push_str(&format!("    pub {}: {},\n", f_name, f_ty));
            *current_line += 1;
        }

        // Explicit fields and auto-properties
        for member in &decl.members {
            match member {
                MemberDecl::Field(f) if !f.is_static => {
                    let f_vis = format_rust_visibility(f.access);
                    let f_name = normalize_field_ident(&f.name);
                    let f_ty = format_rust_owned_type(&f.ty, self.symtab);
                    out.push_str(&format!("    {}{}: {},\n", f_vis, f_name, f_ty));
                    *current_line += 1;
                }
                MemberDecl::Property(p) if !p.is_static && self.is_auto_property(p) => {
                    let p_vis = format_rust_visibility(p.access);
                    let p_name = normalize_field_ident(&p.name);
                    let p_ty = format_rust_owned_type(&p.ty, self.symtab);
                    out.push_str(&format!("    {}{}: {},\n", p_vis, p_name, p_ty));
                    *current_line += 1;
                }
                _ => {}
            }
        }

        out.push_str("}\n");
        *current_line += 1;

        let impl_block = self.emit_impl_block(decl, sourcemap, current_line);
        if !impl_block.is_empty() {
            out.push('\n');
            *current_line += 1;
            out.push_str(&impl_block);
        }

        out
    }

    fn emit_class_archetype(
        &mut self,
        decl: &TypeDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &decl.span);
        let vis = format_rust_visibility(decl.access);
        let generics = format_type_params(&decl.type_params);
        let mut out = format!("{}struct {}{} {{\n", vis, decl.name, generics);
        *current_line += 1;

        // If `FlattenedSubStruct`, embed `pub base: BaseStruct` as the first field
        let mut flattened_base_name: Option<String> = None;
        if let PolymorphismStrategy::FlattenedSubStruct { base_type } = &decl.inferred_polymorphism
        {
            if let Some(bsym) = self.symtab.types.get(base_type) {
                let base_struct_name = if bsym.is_abstract {
                    format!("{}Base", bsym.name)
                } else {
                    bsym.name.clone()
                };
                out.push_str(&format!("    pub base: {},\n", base_struct_name));
                *current_line += 1;
                flattened_base_name = Some(base_struct_name);
            }
        }

        for member in &decl.members {
            match member {
                MemberDecl::Field(f) if !f.is_static => {
                    let f_vis = format_rust_visibility(f.access);
                    let f_name = normalize_field_ident(&f.name);
                    let inner_ty = format_rust_owned_type(&f.ty, self.symtab);
                    let storage_ty = wrap_field_storage(&inner_ty, f.resolved_storage);
                    out.push_str(&format!("    {}{}: {},\n", f_vis, f_name, storage_ty));
                    *current_line += 1;
                }
                MemberDecl::Property(p) if !p.is_static && self.is_auto_property(p) => {
                    let p_vis = format_rust_visibility(p.access);
                    let p_name = normalize_field_ident(&p.name);
                    let inner_ty = format_rust_owned_type(&p.ty, self.symtab);
                    let storage_ty = wrap_field_storage(&inner_ty, p.resolved_storage);
                    out.push_str(&format!("    {}{}: {},\n", p_vis, p_name, storage_ty));
                    *current_line += 1;
                }
                _ => {}
            }
        }

        out.push_str("}\n");
        *current_line += 1;

        if let Some(base_name) = &flattened_base_name {
            out.push('\n');
            *current_line += 1;
            out.push_str(&self.emit_flattened_deref_impl(decl, base_name, current_line));
        }

        let impl_block = self.emit_impl_block(decl, sourcemap, current_line);
        if !impl_block.is_empty() {
            out.push('\n');
            *current_line += 1;
            out.push_str(&impl_block);
        }

        if decl.has_disposable_drop {
            if let Some(dispose_method) = decl.members.iter().find_map(|m| match m {
                MemberDecl::Method(md) if md.name == "Dispose" && md.params.is_empty() => Some(md),
                _ => None,
            }) {
                out.push('\n');
                *current_line += 1;
                out.push_str(&self.emit_drop_impl(decl, dispose_method, sourcemap, current_line));
            }
        }

        out
    }

    fn emit_closed_world_enum_hierarchy(
        &mut self,
        base: &TypeDecl,
        variants: &[&TypeDecl],
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &base.span);
        let vis = format_rust_visibility(base.access);
        let base_struct_name = format!("{}Base", base.name);
        let mut out = String::new();

        // 1. Emit `<Base>Base` struct holding shared state fields/auto-properties
        out.push_str("#[derive(Clone, Debug, PartialEq)]\n");
        *current_line += 1;
        out.push_str(&format!("{}struct {} {{\n", vis, base_struct_name));
        *current_line += 1;

        for member in &base.members {
            match member {
                MemberDecl::Field(f) if !f.is_static => {
                    let f_name = normalize_field_ident(&f.name);
                    let f_ty = format_rust_owned_type(&f.ty, self.symtab);
                    out.push_str(&format!("    pub {}: {},\n", f_name, f_ty));
                    *current_line += 1;
                }
                MemberDecl::Property(p) if !p.is_static && self.is_auto_property(p) => {
                    let p_name = normalize_field_ident(&p.name);
                    let p_ty = format_rust_owned_type(&p.ty, self.symtab);
                    out.push_str(&format!("    pub {}: {},\n", p_name, p_ty));
                    *current_line += 1;
                }
                _ => {}
            }
        }
        out.push_str("}\n\n");
        *current_line += 2;

        // 2. Emit each concrete subclass struct with `pub base: <Base>Base` + `Deref`/`DerefMut`
        for &vdecl in variants {
            out.push_str(&self.emit_class_archetype(vdecl, sourcemap, current_line));
            out.push('\n');
            *current_line += 1;
        }

        // 3. Emit the closed-world tagged union `pub enum <Base>`
        out.push_str(&format!("{}enum {} {{\n", vis, base.name));
        *current_line += 1;
        for &vdecl in variants {
            let tag = strip_base_suffix(&vdecl.name, &base.name);
            out.push_str(&format!("    {}({}),\n", tag, vdecl.name));
            *current_line += 1;
        }
        out.push_str("}\n\n");
        *current_line += 2;

        // 4. Emit exhaustive `match` dispatch methods on `impl <Base>` for abstract/virtual methods
        out.push_str(&format!("impl {} {{\n", base.name));
        *current_line += 1;

        for member in &base.members {
            if let MemberDecl::Method(m) = member {
                if m.is_abstract || m.is_virtual {
                    let fn_name = if m.disambiguated_rust_name.is_empty() {
                        pascal_to_snake_case(&m.name)
                    } else {
                        m.disambiguated_rust_name.clone()
                    };
                    let ret_str = self.format_method_return_type(m);
                    let params_str = self.format_method_params(m);
                    out.push_str(&format!(
                        "    pub fn {}({}){} {{\n",
                        fn_name, params_str, ret_str
                    ));
                    *current_line += 1;
                    out.push_str("        match self {\n");
                    *current_line += 1;

                    let forward_args: Vec<String> =
                        m.params.iter().map(|p| normalize_local_ident(&p.name)).collect();

                    for &vdecl in variants {
                        let tag = strip_base_suffix(&vdecl.name, &base.name);
                        out.push_str(&format!(
                            "            {}::{}(inner) => inner.{}({}),\n",
                            base.name,
                            tag,
                            fn_name,
                            forward_args.join(", ")
                        ));
                        *current_line += 1;
                    }
                    out.push_str("        }\n");
                    *current_line += 1;
                    out.push_str("    }\n");
                    *current_line += 1;
                }
            }
        }

        out.push_str("}\n");
        *current_line += 1;
        out
    }

    fn emit_flattened_deref_impl(
        &self,
        sub: &TypeDecl,
        base_name: &str,
        current_line: &mut u32,
    ) -> String {
        let mut out = String::new();
        out.push_str(&format!("impl std::ops::Deref for {} {{\n", sub.name));
        out.push_str(&format!("    type Target = {};\n", base_name));
        out.push_str("    fn deref(&self) -> &Self::Target {\n");
        out.push_str("        &self.base\n");
        out.push_str("    }\n");
        out.push_str("}\n\n");
        out.push_str(&format!("impl std::ops::DerefMut for {} {{\n", sub.name));
        out.push_str("    fn deref_mut(&mut self) -> &mut Self::Target {\n");
        out.push_str("        &mut self.base\n");
        out.push_str("    }\n");
        out.push_str("}\n");
        *current_line += 13;
        out
    }

    fn emit_open_trait(
        &mut self,
        decl: &TypeDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &decl.span);
        let vis = format_rust_visibility(decl.access);
        let generics = format_type_params(&decl.type_params);
        let mut out = format!("{}trait {}{} {{\n", vis, decl.name, generics);
        *current_line += 1;

        for member in &decl.members {
            if let MemberDecl::Method(m) = member {
                let fn_name = if m.disambiguated_rust_name.is_empty() {
                    pascal_to_snake_case(&m.name)
                } else {
                    m.disambiguated_rust_name.clone()
                };
                let params_str = self.format_method_params(m);
                let ret_str = self.format_method_return_type(m);
                out.push_str(&format!("    fn {}({}){};\n", fn_name, params_str, ret_str));
                *current_line += 1;
            }
        }

        out.push_str("}\n");
        *current_line += 1;
        out
    }

    fn emit_enum_decl(
        &mut self,
        decl: &TypeDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &decl.span);
        let vis = format_rust_visibility(decl.access);
        let mut out = String::from("#[derive(Clone, Debug, PartialEq)]\n");
        *current_line += 1;
        out.push_str(&format!("{}enum {} {{\n", vis, decl.name));
        *current_line += 1;

        for v in &decl.enum_variants {
            if v.payload.is_empty() {
                out.push_str(&format!("    {},\n", v.name));
            } else {
                let types: Vec<String> = v
                    .payload
                    .iter()
                    .map(|p| format_rust_owned_type(&p.ty, self.symtab))
                    .collect();
                out.push_str(&format!("    {}({}),\n", v.name, types.join(", ")));
            }
            *current_line += 1;
        }

        out.push_str("}\n");
        *current_line += 1;
        out
    }

    fn emit_impl_block(
        &mut self,
        decl: &TypeDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        let mut items = Vec::new();

        for member in &decl.members {
            match member {
                MemberDecl::Constructor(ctor) if !ctor.is_extern => {
                    items.push(self.emit_constructor(decl, ctor, sourcemap, current_line));
                }
                MemberDecl::Method(method) => {
                    // `Dispose()` is emitted inside `impl Drop` instead of the inherent `impl`
                    if decl.has_disposable_drop
                        && method.name == "Dispose"
                        && method.params.is_empty()
                    {
                        continue;
                    }
                    // `extern` methods are implemented in a co-located `.rs` file
                    if method.is_extern || method.is_abstract {
                        continue;
                    }
                    items.push(self.emit_method(decl, method, sourcemap, current_line));
                }
                _ => {}
            }
        }

        if items.is_empty() {
            return String::new();
        }

        let generics = format_type_params(&decl.type_params);
        let mut out = format!("impl{} {}{} {{\n", generics, decl.name, generics);
        *current_line += 1;
        out.push_str(&items.join("\n\n"));
        out.push_str("\n}\n");
        *current_line += 2;
        out
    }

    fn emit_constructor(
        &mut self,
        decl: &TypeDecl,
        ctor: &ConstructorDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &ctor.span);
        let vis = format_rust_visibility(ctor.access);
        let fn_name = if ctor.disambiguated_rust_name.is_empty() {
            "new"
        } else {
            &ctor.disambiguated_rust_name
        };

        let params: Vec<String> = ctor
            .params
            .iter()
            .map(|p| {
                let p_name = normalize_local_ident(&p.name);
                let p_ty = format_rust_param_type(&p.ty, p.inferred_borrow, self.symtab);
                format!("{}: {}", p_name, p_ty)
            })
            .collect();

        let mut out = format!("    {}fn {}({}) -> Self {{\n", vis, fn_name, params.join(", "));
        *current_line += 1;

        // Collect field assignments from the constructor body (`_tax = tax;`)
        let mut assigned_fields = Vec::new();
        if let Some(body) = &ctor.body {
            let mut expr_emitter = RustExprEmitter::new(self.symtab, Some(decl.id));
            for stmt in &body.stmts {
                if let Stmt::ExprStmt { expr, .. } = stmt {
                    if let crate::frontend::ast::ExprKind::Assignment { target, value, .. } =
                        &expr.kind
                    {
                        let raw_lhs = match &target.kind {
                            crate::frontend::ast::ExprKind::Identifier { name, .. } => {
                                Some(normalize_field_ident(name))
                            }
                            crate::frontend::ast::ExprKind::MemberAccess { member, .. } => {
                                Some(normalize_field_ident(member))
                            }
                            _ => None,
                        };
                        if let Some(field_name) = raw_lhs {
                            let rhs_str = expr_emitter.emit_expr(value);
                            if field_name == rhs_str {
                                assigned_fields.push(field_name);
                            } else {
                                assigned_fields.push(format!("{}: {}", field_name, rhs_str));
                            }
                        }
                    }
                }
            }
        }

        out.push_str(&format!("        Self {{ {} }}\n", assigned_fields.join(", ")));
        *current_line += 1;
        out.push_str("    }");
        *current_line += 1;
        out
    }

    fn emit_method(
        &mut self,
        decl: &TypeDecl,
        method: &MethodDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &method.span);
        let vis = format_rust_visibility(method.access);
        let async_kw = if method.is_async { "async " } else { "" };
        let fn_name = if method.disambiguated_rust_name.is_empty() {
            pascal_to_snake_case(&method.name)
        } else {
            method.disambiguated_rust_name.clone()
        };
        let generics = format_type_params(&method.type_params);
        let params_str = self.format_method_params(method);
        let ret_str = self.format_method_return_type(method);

        let mut out = format!(
            "    {}{}fn {}{}({}){} {{\n",
            vis, async_kw, fn_name, generics, params_str, ret_str
        );
        *current_line += 1;

        if let Some(body) = &method.body {
            let mut expr_emitter = RustExprEmitter::new(self.symtab, Some(decl.id));
            expr_emitter.is_fallible_method =
                matches!(method.inferred_effect, EffectSignature::Fallible { .. });
            expr_emitter.is_void_return = method.return_type.short_name() == "void";
            for p in &method.params {
                expr_emitter
                    .method_param_borrows
                    .insert(p.name.clone(), p.inferred_borrow);
            }

            let body_rendered = expr_emitter.emit_block(body, 2, sourcemap, current_line);
            if !body_rendered.is_empty() {
                out.push_str(&body_rendered);
                out.push('\n');
            }
        }

        out.push_str("    }");
        *current_line += 1;
        out
    }

    fn emit_drop_impl(
        &mut self,
        decl: &TypeDecl,
        dispose_method: &MethodDecl,
        sourcemap: &mut RustSourceMap,
        current_line: &mut u32,
    ) -> String {
        sourcemap.record(*current_line, &dispose_method.span);
        let mut out = format!("impl Drop for {} {{\n", decl.name);
        out.push_str("    fn drop(&mut self) {\n");
        *current_line += 2;

        if let Some(body) = &dispose_method.body {
            let mut expr_emitter = RustExprEmitter::new(self.symtab, Some(decl.id));
            let rendered = expr_emitter.emit_block(body, 2, sourcemap, current_line);
            if !rendered.is_empty() {
                out.push_str(&rendered);
                out.push('\n');
            }
        }

        out.push_str("    }\n}\n");
        *current_line += 2;
        out
    }

    fn format_method_params(&self, method: &MethodDecl) -> String {
        let mut parts = Vec::new();
        if !method.is_static {
            let self_str = match method.inferred_self_borrow {
                BorrowMode::MutBorrow => "&mut self",
                BorrowMode::OwnedMove => "self",
                _ => "&self",
            };
            parts.push(self_str.to_string());
        }

        for p in &method.params {
            let p_name = normalize_local_ident(&p.name);
            let p_ty = format_rust_param_type(&p.ty, p.inferred_borrow, self.symtab);
            parts.push(format!("{}: {}", p_name, p_ty));
        }

        parts.join(", ")
    }

    fn format_method_return_type(&self, method: &MethodDecl) -> String {
        let base_ret = format_rust_owned_type(&method.return_type, self.symtab);
        match &method.inferred_effect {
            EffectSignature::Fallible { error_type } => {
                let err_str = format_rust_owned_type(error_type, self.symtab);
                format!(" -> Result<{}, {}>", base_ret, err_str)
            }
            _ => {
                if base_ret == "()" {
                    String::new()
                } else {
                    format!(" -> {}", base_ret)
                }
            }
        }
    }

    fn is_auto_property(&self, prop: &crate::frontend::ast::PropertyDecl) -> bool {
        prop.accessors.iter().all(|a| a.body.is_none())
    }

    fn module_uses_arc(&self, types: &[&TypeDecl]) -> bool {
        types.iter().any(|t| {
            matches!(t.kind, TypeKind::ServiceClass)
                || t.members.iter().any(|m| match m {
                    MemberDecl::Field(f) => f.resolved_storage == FieldStorageMode::ArcShared,
                    MemberDecl::Property(p) => p.resolved_storage == FieldStorageMode::ArcShared,
                    _ => false,
                })
        })
    }

    fn module_uses_rwlock(&self, types: &[&TypeDecl]) -> bool {
        types.iter().any(|t| {
            matches!(t.kind, TypeKind::SharedClass)
                || t.members.iter().any(|m| match m {
                    MemberDecl::Field(f) => f.resolved_storage == FieldStorageMode::RwLockShared,
                    MemberDecl::Property(p) => p.resolved_storage == FieldStorageMode::RwLockShared,
                    _ => false,
                })
        })
    }

    fn module_uses_decimal(&self, types: &[&TypeDecl]) -> bool {
        for t in types {
            for p in &t.primary_ctor_params {
                if p.ty.short_name() == "decimal" || p.ty.short_name() == "Decimal" {
                    return true;
                }
            }
            for m in &t.members {
                match m {
                    MemberDecl::Field(f)
                        if f.ty.short_name() == "decimal" || f.ty.short_name() == "Decimal" =>
                    {
                        return true;
                    }
                    MemberDecl::Property(p)
                        if p.ty.short_name() == "decimal" || p.ty.short_name() == "Decimal" =>
                    {
                        return true;
                    }
                    MemberDecl::Method(md) => {
                        if md.return_type.short_name() == "decimal"
                            || md.params.iter().any(|p| p.ty.short_name() == "decimal")
                        {
                            return true;
                        }
                    }
                    _ => {}
                }
            }
        }
        false
    }
}

fn format_rust_visibility(access: AccessMod) -> &'static str {
    match access {
        AccessMod::Public => "pub ",
        AccessMod::Internal | AccessMod::Protected => "pub(crate) ",
        AccessMod::Private => "",
    }
}

fn format_type_params(type_params: &[String]) -> String {
    if type_params.is_empty() {
        String::new()
    } else {
        format!("<{}>", type_params.join(", "))
    }
}

fn wrap_field_storage(inner_ty: &str, mode: FieldStorageMode) -> String {
    match mode {
        FieldStorageMode::Plain => inner_ty.to_string(),
        FieldStorageMode::ArcShared => format!("Arc<{}>", inner_ty),
        FieldStorageMode::RwLockShared => format!("Arc<RwLock<{}>>", inner_ty),
    }
}

fn strip_base_suffix(sub_name: &str, base_name: &str) -> String {
    if let Some(prefix) = sub_name.strip_suffix(base_name) {
        if !prefix.is_empty() {
            return prefix.to_string();
        }
    }
    sub_name.to_string()
}

```

---

### `src/codegen/cargo_synthesizer.rs`

```rust
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::codegen::rs_ast_emitter::RustModuleEmitter;
use crate::codegen::sourcemap::RustSourceMap;
use crate::frontend::ast::{CompilationUnit, TypeDecl};
use crate::project::RsProjConfig;
use crate::semantics::symbols::{pascal_to_snake_case, GlobalSymbolTable, NamespaceModulePlan};

/// Output artifact summary produced by Pass 3 (`CargoWorkspaceSynthesizer`).
#[derive(Clone, Debug)]
pub struct SynthesizedCrateOutput {
    pub cargo_toml_path: PathBuf,
    pub cargo_toml_content: String,
    pub lib_rs_path: PathBuf,
    pub lib_rs_content: String,
    /// Map of relative path (e.g. `"src/commerce/checkout.rs"`) -> emitted Rust code.
    pub emitted_modules: BTreeMap<String, String>,
    /// Map of relative path -> bidirectional `.rsharp` <-> `.rs` source map.
    pub sourcemaps: BTreeMap<String, RustSourceMap>,
    /// Co-located `.rs` files copied and linked into the synthesized crate.
    pub linked_colocated_files: Vec<String>,
}

/// Pass 3 Cargo Workspace & Module Tree Synthesizer.
///
/// Groups all decorated `.rsharp` types by their logical virtual namespace, emits formatted
/// `src/<namespace>.rs` modules, links any co-located raw `.rs` files (`extern partial`)
/// into the module tree, writes `.rsharp.map` bidirectional source maps, and synthesizes
/// `Cargo.toml` and `src/lib.rs`.
pub struct CargoWorkspaceSynthesizer;

impl CargoWorkspaceSynthesizer {
    /// Generates all in-memory Rust modules, `Cargo.toml`, `src/lib.rs`, and `.rsharp.map` tables.
    pub fn synthesize_in_memory(
        config: &RsProjConfig,
        symtab: &GlobalSymbolTable,
        units: &[CompilationUnit],
    ) -> Result<SynthesizedCrateOutput, String> {
        let plans = symtab.build_namespace_module_plans();
        let mut emitted_modules = BTreeMap::new();
        let mut sourcemaps = BTreeMap::new();
        let mut linked_colocated_files = Vec::new();

        // Map co-located `.rs` file stems (e.g. `"PacketHeader"`) to their raw `.rs` paths
        let mut colocated_by_stem: BTreeMap<String, &PathBuf> = BTreeMap::new();
        for rs_path in &config.colocated_rs_files {
            if let Some(stem) = rs_path.file_stem().and_then(|s| s.to_str()) {
                colocated_by_stem.insert(stem.to_string(), rs_path);
            }
        }

        let mut emitter = RustModuleEmitter::new(symtab);

        for plan in &plans {
            // Collect all non-ambient AST `TypeDecl`s belonging to `plan.namespace`
            let mut ns_decls: Vec<&TypeDecl> = Vec::new();
            for unit in units {
                if unit.is_ambient_stub || unit.namespace != plan.namespace {
                    continue;
                }
                for decl in &unit.types {
                    ns_decls.push(decl);
                }
            }

            let (mut rs_code, smap) =
                emitter.emit_namespace_module(&plan.namespace, &ns_decls, &plan.target_rs_file);

            // Check if any type in this namespace has a matching co-located `.rs` file (`extern partial`)
            for decl in &ns_decls {
                if let Some(&colocated_path) = colocated_by_stem.get(&decl.name) {
                    let submod_snake = format!("{}_ext", pascal_to_snake_case(&decl.name));
                    let parent_dir = Path::new(&plan.target_rs_file)
                        .parent()
                        .unwrap_or_else(|| Path::new("src"));
                    let colocated_rel = parent_dir
                        .join(format!("{}.rs", submod_snake))
                        .to_string_lossy()
                        .replace('\\', "/");

                    let raw_rs = fs::read_to_string(colocated_path).map_err(|e| {
                        format!(
                            "Failed to read co-located Rust file '{}': {}",
                            colocated_path.display(),
                            e
                        )
                    })?;

                    rs_code.push_str(&format!(
                        "\n// Linked co-located raw Rust implementation (`{}`)\n#[path = \"{}.rs\"]\npub mod {};\n",
                        colocated_path
                            .file_name()
                            .and_then(|s| s.to_str())
                            .unwrap_or(""),
                        submod_snake,
                        submod_snake
                    ));

                    emitted_modules.insert(colocated_rel.clone(), raw_rs);
                    linked_colocated_files.push(colocated_rel);
                }
            }

            emitted_modules.insert(plan.target_rs_file.clone(), rs_code);
            sourcemaps.insert(plan.target_rs_file.clone(), smap);
        }

        let cargo_toml_content = Self::emit_cargo_toml(config);
        let lib_rs_content = Self::emit_lib_rs(&plans);

        Ok(SynthesizedCrateOutput {
            cargo_toml_path: config.out_cargo_dir.join("Cargo.toml"),
            cargo_toml_content,
            lib_rs_path: config.out_cargo_dir.join("src").join("lib.rs"),
            lib_rs_content,
            emitted_modules,
            sourcemaps,
            linked_colocated_files,
        })
    }

    /// Synthesizes the complete Cargo workspace on disk inside `config.out_cargo_dir`.
    pub fn synthesize_workspace(
        config: &RsProjConfig,
        symtab: &GlobalSymbolTable,
        units: &[CompilationUnit],
    ) -> Result<SynthesizedCrateOutput, String> {
        let output = Self::synthesize_in_memory(config, symtab, units)?;

        fs::create_dir_all(config.out_cargo_dir.join("src"))
            .map_err(|e| format!("Failed to create output src directory: {}", e))?;

        fs::write(&output.cargo_toml_path, &output.cargo_toml_content)
            .map_err(|e| format!("Failed to write Cargo.toml: {}", e))?;

        fs::write(&output.lib_rs_path, &output.lib_rs_content)
            .map_err(|e| format!("Failed to write src/lib.rs: {}", e))?;

        for (rel_path, code) in &output.emitted_modules {
            let full_path = config.out_cargo_dir.join(rel_path);
            if let Some(parent) = full_path.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            fs::write(&full_path, code)
                .map_err(|e| format!("Failed to write '{}': {}", full_path.display(), e))?;
        }

        for (rel_path, smap) in &output.sourcemaps {
            let map_path = config.out_cargo_dir.join(format!("{}.rsharp.map", rel_path));
            if let Some(parent) = map_path.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            fs::write(&map_path, smap.to_map_file_string())
                .map_err(|e| format!("Failed to write '{}': {}", map_path.display(), e))?;
        }

        Ok(output)
    }

    pub fn emit_cargo_toml(config: &RsProjConfig) -> String {
        let mut out = String::from("# Auto-generated by rsharpc — DO NOT EDIT\n");
        out.push_str("[package]\n");
        out.push_str(&format!("name = \"{}\"\n", config.name));
        out.push_str(&format!("version = \"{}\"\n", config.version));
        out.push_str(&format!("edition = \"{}\"\n\n", config.edition));
        out.push_str("[dependencies]\n");
        for (crate_name, ver) in &config.cargo_dependencies {
            out.push_str(&format!("{} = \"{}\"\n", crate_name, ver));
        }
        out
    }

    pub fn emit_lib_rs(plans: &[NamespaceModulePlan]) -> String {
        let mut out = String::from("// Auto-generated by rsharpc — DO NOT EDIT\n");

        // Group namespaces by top-level and nested module segments
        let mut top_level_children: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        let mut single_segment_mods: BTreeSet<String> = BTreeSet::new();

        for plan in plans {
            if plan.rust_mod_segments.len() == 1 {
                single_segment_mods.insert(plan.rust_mod_segments[0].clone());
            } else if plan.rust_mod_segments.len() >= 2 {
                let root = plan.rust_mod_segments[0].clone();
                let child = plan.rust_mod_segments[1..].join("::");
                top_level_children.entry(root).or_default().insert(child);
            }
        }

        for m in &single_segment_mods {
            if !top_level_children.contains_key(m) {
                out.push_str(&format!("pub mod {};\n", m));
            }
        }

        for (root, children) in &top_level_children {
            out.push_str(&format!("pub mod {} {{\n", root));
            for child in children {
                let leaf = child.split("::").last().unwrap_or(child);
                out.push_str(&format!("    pub mod {};\n", leaf));
            }
            out.push_str("}\n");
        }

        out
    }
}

```

---

### `src/codegen/mod.rs`

```rust
pub mod cargo_synthesizer;
pub mod expr_emitter;
pub mod rs_ast_emitter;
pub mod sourcemap;

pub use cargo_synthesizer::{CargoWorkspaceSynthesizer, SynthesizedCrateOutput};
pub use expr_emitter::RustExprEmitter;
pub use rs_ast_emitter::RustModuleEmitter;
pub use sourcemap::{RustSourceMap, SourceMapEntry};

```

---

### `src/lib.rs`

```rust
pub mod codegen;
pub mod diagnostics;
pub mod frontend;
pub mod project;
pub mod semantics;

use std::fs;
use std::path::Path;

use codegen::{CargoWorkspaceSynthesizer, SynthesizedCrateOutput};
use diagnostics::DiagnosticEngine;
use frontend::{CompilationUnit, Lexer, Parser};
use project::{load_rsproj, RsProjConfig};
use semantics::{
    analyze_archetypes, collect_global_symbols, fuse_linq_pipelines, infer_checked_effects,
    resolve_overloads, resolve_polymorphism_strategies, resolve_primitives,
    run_preflight_ownership_checks, GlobalSymbolTable, InterproceduralBorrowInferencer,
};

/// Convenience helper to lex and parse a single `.rsharp` or `.d.rsharp` source string.
pub fn parse_source_str(
    source: &str,
    file_id: usize,
    filename: &str,
    diag: &mut DiagnosticEngine,
) -> CompilationUnit {
    let tokens = {
        let mut lexer = Lexer::new(source, file_id, filename, diag);
        lexer.tokenize()
    };
    let mut parser = Parser::new(tokens, file_id, filename, diag);
    parser.parse_compilation_unit()
}

/// Runs Milestone 1 (Frontend Lexer + Parser) and Milestone 2 (Pass 1 Global Symbol Collector
/// & Virtual Namespace Aggregator) over an in-memory set of `(filename, source_code)` pairs.
pub fn analyze_workspace_pass1(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let mut diag = DiagnosticEngine::new();
    let mut units = Vec::with_capacity(files.len());

    for (idx, (filename, source)) in files.iter().enumerate() {
        let unit = parse_source_str(source, idx, filename, &mut diag);
        units.push(unit);
    }

    let mut symtab = GlobalSymbolTable::new();
    collect_global_symbols(&mut units, &mut symtab, &mut diag);

    (units, symtab, diag)
}

/// Runs Milestone 1, Milestone 2 (Pass 1), and Milestone 3 (Pass 2A: Archetype Lowering,
/// Hierarchy Flattening & Static Overload Resolution) across all workspace files.
pub fn analyze_workspace_pass2a(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (mut units, mut symtab, mut diag) = analyze_workspace_pass1(files);
    if !diag.has_errors() {
        analyze_archetypes(&mut units, &mut symtab, &mut diag);
        resolve_polymorphism_strategies(&mut units, &mut symtab);
        resolve_overloads(&mut units, &mut symtab);
    }
    (units, symtab, diag)
}

/// Runs Milestones 1–4 (Pass 1, Pass 2A, and Pass 2B: `primitive` Type Erasure,
/// Interprocedural Borrow & Mutation Propagation, Checked `throws` Effect Inference,
/// and Zero-Cost LINQ-to-Iterator Pipeline Fusion).
pub fn analyze_workspace_pass2b(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (mut units, mut symtab, diag) = analyze_workspace_pass2a(files);
    if !diag.has_errors() {
        resolve_primitives(&mut units, &mut symtab);
        InterproceduralBorrowInferencer::infer_all(&mut units, &mut symtab);
        infer_checked_effects(&mut units, &mut symtab);
        fuse_linq_pipelines(&mut units, &symtab);
    }
    (units, symtab, diag)
}

/// Runs Milestones 1–5 (Pass 1, Pass 2A, Pass 2B, and Pass 2.5 Pre-Flight Ownership Verifier
/// enforcing rules `RSHARP001`–`RSHARP003` before Rust code emission).
pub fn analyze_workspace_with_preflight(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (units, symtab, mut diag) = analyze_workspace_pass2b(files);
    if !diag.has_errors() {
        run_preflight_ownership_checks(&units, &symtab, &mut diag);
    }
    (units, symtab, diag)
}

/// Full 3-pass compiler pipeline (Milestones 1–6) from an on-disk `.rsproj` file:
/// - Discovers all `.d.rsharp`, `.rsharp`, and co-located `.rs` files.
/// - Runs Pass 1 (Global Symbol Table), Pass 2A/2B (Archetype, Hierarchy, Overload, Borrow,
///   Effect & LINQ Analysis), and Pass 2.5 (Pre-Flight Ownership Verifier).
/// - Runs Pass 3 (`CargoWorkspaceSynthesizer`) if `write_to_disk` is true or returns the
///   in-memory synthesized crate output.
pub fn compile_rsproj(
    rsproj_path: &Path,
    stdlib_dir: Option<&Path>,
    write_to_disk: bool,
) -> Result<(RsProjConfig, SynthesizedCrateOutput, DiagnosticEngine), String> {
    let config = load_rsproj(rsproj_path, stdlib_dir)?;
    let input_paths = config.all_rsharp_inputs();

    let mut loaded_sources: Vec<(String, String)> = Vec::with_capacity(input_paths.len());
    for path in &input_paths {
        let src = fs::read_to_string(path)
            .map_err(|e| format!("Failed to read '{}': {}", path.display(), e))?;
        let display_name = path
            .strip_prefix(&config.root_dir)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/");
        loaded_sources.push((display_name, src));
    }

    let borrowed_pairs: Vec<(&str, &str)> = loaded_sources
        .iter()
        .map(|(f, s)| (f.as_str(), s.as_str()))
        .collect();

    let (units, mut symtab, diag) = analyze_workspace_with_preflight(&borrowed_pairs);
    symtab.colocated_rs_files = config.colocated_rs_files.clone();

    if diag.has_errors() {
        return Err(diag.format_all());
    }

    let synth = if write_to_disk {
        CargoWorkspaceSynthesizer::synthesize_workspace(&config, &symtab, &units)?
    } else {
        CargoWorkspaceSynthesizer::synthesize_in_memory(&config, &symtab, &units)?
    };

    Ok((config, synth, diag))
}

```

---

### `src/main.rs`

```rust
use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

use rsharpc::compile_rsproj;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        print_usage();
        return ExitCode::from(1);
    }

    let subcommand = args[1].as_str();
    let rsproj_path = Path::new(&args[2]);

    // Locate ambient `stdlib/` directory relative to the current working directory if present
    let default_stdlib = PathBuf::from("stdlib");
    let stdlib_dir = if default_stdlib.exists() {
        Some(default_stdlib.as_path())
    } else {
        None
    };

    match subcommand {
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
}

```

---

### `tests/fixtures/commerce_workspace/Commerce.rsproj`

```xml
<Project Sdk="RustSharp.Sdk">
  <PropertyGroup>
    <AssemblyName>commerce_workspace</AssemblyName>
    <Version>0.1.0</Version>
    <RustEdition>2021</RustEdition>
    <OutputPath>target/rsharp_synth</OutputPath>
  </PropertyGroup>
  <ItemGroup>
    <CargoCrate Include="rust_decimal" Version="1.36" />
  </ItemGroup>
</Project>

```

---

### `tests/fixtures/commerce_workspace/Features/Checkout/OrderHandler.rsharp`

```csharp
namespace Commerce.Checkout;

extern using rust_decimal::Decimal as Decimal;

public record Order(int Id, decimal Total);
public record ValidationError(string Reason);

public service class TaxCalculator
{
    public void RecordAudit(Order order)
    {
    }
}

public service class OrderHandler
{
    private readonly TaxCalculator _tax;

    public OrderHandler(TaxCalculator tax) => _tax = tax;

    public void Checkout(Order order, string coupon) throws ValidationError
    {
        if (order.Total <= 0.0m)
            throw new ValidationError("Order total must be positive");

        ApplyCoupon(order, coupon);
        _tax.RecordAudit(order);
    }

    private void ApplyCoupon(Order order, string code)
    {
        if (code == "SAVE10")
            order.Total -= 10.0m;
    }
}

```

---

### `tests/fixtures/commerce_workspace/Features/Payments/PaymentHierarchy.rsharp`

```csharp
namespace Commerce.Payments;

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

```

---

### `tests/fixtures/commerce_workspace/Ingest/PacketHeader.rsharp`

```csharp
namespace Commerce.Ingest;

public partial struct PacketHeader
{
    public uint Magic;
    public ushort Version;
    public ushort PayloadLen;

    public static extern PacketHeader? TryParse(ReadOnlySpan<byte> buffer);
}

```

---

### `tests/fixtures/commerce_workspace/Ingest/PacketHeader.rs`

```rust
use super::PacketHeader;

impl PacketHeader {
    pub fn try_parse(buffer: &[u8]) -> Option<PacketHeader> {
        if buffer.len() < 8 {
            return None;
        }
        let magic = u32::from_le_bytes([buffer[0], buffer[1], buffer[2], buffer[3]]);
        let version = u16::from_le_bytes([buffer[4], buffer[5]]);
        let payload_len = u16::from_le_bytes([buffer[6], buffer[7]]);
        Some(PacketHeader {
            magic,
            version,
            payload_len,
        })
    }
}

```

---

### `tests/m6_codegen_and_cargo_synth_tests.rs`

```rust
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
    assert!(synth.cargo_toml_content.contains("name = \"commerce_workspace\""));
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
    assert!(checkout_rs.contains("return Err(ValidationError { reason: \"Order total must be positive\".to_string() });"));
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

```

---

### `README.md`

```markdown
# RustSharp Compiler (`rsharpc`) — Phase 1 Prototype

**RustSharp (`.rsharp` / `.d.rsharp`)** is a multi-pass whole-program compiler that pairs **C# Architectural Ergonomics** with **Zero-Cost Idiomatic Rust Code Generation**.

## Core Architectural Pillars

1. **Pass 1 — File-Independent Virtual Namespaces & Global Symbol Table (`src/semantics/collector.rs`):**
   Scans all `.rsharp`, `.d.rsharp`, and co-located `.rs` files in a `.rsproj` workspace simultaneously, decoupling physical directory paths from logical `namespace` declarations and resolving circular cross-file type references.
2. **Pass 2A — Explicit Ownership Archetypes, Zero-VTable Polymorphism & Static Overloads (`src/semantics/`):**
   - `record` / `struct` $\rightarrow$ `#[derive(Clone, Debug, PartialEq)]` linear value structs.
   - `service class` $\rightarrow$ Immutable-after-construction DI singletons (`Arc<T>` fields, `&self` methods).
   - `shared class` $\rightarrow$ Multi-owner interior-mutable state (`Arc<RwLock<T>>`).
   - Closed-world `abstract class` / `interface` hierarchies lower to exhaustive Rust `enum` tagged unions with `Deref` struct flattening; `extensible interface` lowers to `pub trait`.
   - Overloaded methods and constructors are disambiguated statically at compile time (`find_by_id`, `find_by_email`).
3. **Pass 2B — Interprocedural Borrow Propagation, Checked `throws` Effects & LINQ Fusion (`src/semantics/`):**
   - Propagates `BorrowMode` (`&T`, `&mut T`, `T`, `Arc<T>`) bottom-up across the call graph, automatically injecting `let mut` and `&mut` at call sites.
   - Rewrites `throws TError` methods to `Result<T, TError>`, injects `?` on unguarded calls, and lowers `try / catch` into `match`.
   - Fuses chained `.Where().Select().ToList()` queries into zero-allocation `.iter().filter().map().collect()` pipelines.
4. **Pass 2.5 — Pre-Flight Ownership Verifier (`src/semantics/preflight_verifier.rs`):**
   Halts before `rustc` with C#-ergonomic diagnostics pointing to exact `.rsharp` lines and columns:
   - `RSHARP001`: Field mutation inside a `service class` outside its constructor.
   - `RSHARP002`: Mutating a collection while iterating over it in a `foreach` loop.
   - `RSHARP003`: Use-after-move of a linear / `IDisposable` resource.
5. **Pass 3 — Idiomatic Rust Emitter, Co-Located `.rs` Linker & Cargo Synthesizer (`src/codegen/`):**
   Synthesizes a complete Cargo crate (`Cargo.toml`, `src/lib.rs`, `src/<namespace>.rs`), links co-located raw `.rs` files (`extern partial`) in the same crate with zero FFI overhead, and emits `.rsharp.map` bidirectional line mappings.

## CLI Usage

```bash
# Run Pass 1, Pass 2, and Pass 2.5 pre-flight verification
cargo run -- check tests/fixtures/commerce_workspace/Commerce.rsproj

# Emit synthesized Cargo workspace and .rsharp.map source maps
cargo run -- emit-rs tests/fixtures/commerce_workspace/Commerce.rsproj

# Run the complete Milestone 1–6 verification test suite
cargo test

```

```

---

All **6 Milestones (M1–M6)** of the **RustSharp Compiler (`rsharpc`)** Phase 1 prototype are now complete[cite: 1]. Let me know if you would like to explore **Phase 3 (`rsharp-bindgen` Cargo stub generator)**, **Phase 4 (Attributes-to-Macros & Tokio `async` lowering)**, or **Phase 5 (`rsharp-lsp` Language Server)** next[cite: 1]!

```
