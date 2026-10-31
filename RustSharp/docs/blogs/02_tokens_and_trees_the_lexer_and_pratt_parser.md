# Under the Hood of RustSharp: Blog 02
# Tokens & Trees — The UTF-8 Lexer and Pratt Expression Parser

> *Part 2 of the 12-part technical series "Under the Hood of RustSharp: From C# Ergonomics to Pure Zero-Cost Rust"*

---

## 1. The Challenge of C# Grammar in Pure Standard Library Rust

A primary architectural decision of RustSharp (**Decision D-013**) is that the entire compiler toolchain (`rsharpc`) must be implemented in **100% pure standard library Rust (`std`) with zero external crate dependencies**. We do not use `nom`, `pest`, `lalrpop`, or `syn`. Every token scan, precedence calculation, and AST node allocation is hand-crafted for maximum throughput, memory efficiency, and deterministic control.

Writing a frontend for modern C# is notoriously tricky. Unlike minimal functional languages, C# features:
- Context-sensitive keywords (`record`, `init`, `var`, `service`, `where`, `select`).
- Multi-layered string literal forms: interpolated `$"{x}"`, verbatim `@"C:\path"`, and multiline raw `"""..."""`.
- High operator density with delicate precedence: null-coalescing (`??`), null-conditional (`?.`), range slicing (`1..^1`), lambda arrows (`=>`), and ternary conditionals (`? :`).

In this post, we look under the hood of [`src/frontend/lexer.rs`](file:///home/abhijit/Videos/transpilers/RustSharp/src/frontend/lexer.rs) and [`src/frontend/parser.rs`](file:///home/abhijit/Videos/transpilers/RustSharp/src/frontend/parser.rs) to see how RustSharp parses C# into a high-performance Abstract Syntax Tree.

---

## 2. Fast UTF-8 Scanning: The Lexer

The RustSharp lexer operates directly over UTF-8 string slices (`&str`). It tracks 1-indexed source locations (`SourceSpan { filename, start_line, start_col, end_line, end_col }`) to deliver accurate compiler diagnostics and IDE jump-to-definition targets.

```mermaid
flowchart TD
    Raw["Raw UTF-8 Stream: string text = $\"Hello {name}\";"] --> Lexer["src/frontend/lexer.rs\n- Peekable Char Cursor\n- Fast-path ASCII Dispatch\n- Interpolation Segmenter"]
    Lexer --> T1["Token::Ident('string')"]
    Lexer --> T2["Token::Ident('text')"]
    Lexer --> T3["Token::Eq"]
    Lexer --> T4["Token::InterpolatedString(parts)"]
    Lexer --> T5["Token::Semicolon"]
```

### Handling Interpolated Strings
Interpolated strings ($"Hello {name}, balance: {balance:C}") are tokenized into structured segments rather than raw text:

```rust
#[derive(Clone, Debug, PartialEq)]
pub enum InterpolatedPart {
    Literal(String),
    Expression(String),
}
```

When the lexer encounters `$"`:
1. It maintains a bracket-depth counter (`{` and `}`).
2. Characters outside braces are accumulated into `InterpolatedPart::Literal`.
3. Characters inside `{ ... }` are extracted as raw expressions and stored in `InterpolatedPart::Expression`.
4. The parser later feeds each extracted expression string through a sub-parser instance to produce validated AST expression nodes.

### Decimal and Numerical Literals
In financial C#, `10.50m` denotes an exact 128-bit decimal literal. The lexer recognizes the `m` or `M` suffix:

```rust
// In src/frontend/lexer.rs
if is_decimal {
    Token::DecimalLiteral(raw_digits)
} else if is_float {
    Token::FloatLiteral(raw_float)
} else {
    Token::IntLiteral(raw_int)
}
```

This prevents any precision-destroying conversion to standard floating-point numbers during compilation. In Pass 3, `10.50m` is lowered directly into `rust_decimal::Decimal::new(1050, 2)`.

---

## 3. Top-Down Operator Precedence: The Pratt Parser

Traditional recursive-descent parsers struggle with complex expression grammars. You either end up with 30 nested grammar functions (`parse_relational`, `parse_additive`, `parse_multiplicative`, `parse_bitwise`) which blow out the call stack, or ambiguous shift-reduce conflicts.

RustSharp solves this with an elegant **Pratt Parser** (Top-Down Operator Precedence).

### The Mechanics of Binding Power
Every operator is assigned a left and right binding power (`(u8, u8)`). An operator with higher binding power "pulls" operands more tightly than one with lower binding power:

```rust
// Precedence hierarchy in src/frontend/parser.rs
fn infix_binding_power(op: &Token) -> Option<(u8, u8)> {
    match op {
        Token::QuestionQuestion => Some((3, 4)),      // Null-coalescing: a ?? b
        Token::PipePipe => Some((5, 6)),              // Logical OR: a || b
        Token::AmpAmp => Some((7, 8)),                // Logical AND: a && b
        Token::Pipe => Some((9, 10)),                 // Bitwise OR: a | b
        Token::Caret => Some((11, 12)),               // Bitwise XOR: a ^ b
        Token::Amp => Some((13, 14)),                 // Bitwise AND: a & b
        Token::EqEq | Token::BangEq => Some((15, 16)), // Equality: a == b
        Token::Lt | Token::LtEq | Token::Gt | Token::GtEq => Some((17, 18)),
        Token::DotDot => Some((19, 20)),              // Range: 0..10
        Token::Plus | Token::Minus => Some((21, 22)), // Additive: a + b
        Token::Star | Token::Slash | Token::Percent => Some((23, 24)), // Multiplicative
        _ => None,
    }
}
```

The core loop in `parse_expr_bp(min_bp)` evaluates expressions in linear time without recursion overflow:

```rust
fn parse_expr_bp(&mut self, min_bp: u8) -> Result<Expr, CompileError> {
    // 1. Parse prefix operator or primary atom (Null-denotation / Nud)
    let mut lhs = self.parse_primary_expr()?;

    // 2. Loop as long as next token's left binding power exceeds current minimum
    loop {
        let op_token = self.peek_token();
        if let Some((l_bp, r_bp)) = infix_binding_power(&op_token) {
            if l_bp < min_bp {
                break;
            }
            self.advance_token();
            let rhs = self.parse_expr_bp(r_bp)?;
            lhs = Expr::Binary {
                op: token_to_bin_op(&op_token),
                lhs: Box::new(lhs),
                rhs: Box::new(rhs),
                inferred_type: None, // Interior decoration slot
            };
            continue;
        }

        // 3. Postfix calls, indexing, and member access (Left-denotation / Led)
        if op_token == Token::Dot {
            self.advance_token();
            let member = self.expect_identifier()?;
            lhs = Expr::MemberAccess {
                target: Box::new(lhs),
                member,
                inferred_type: None,
            };
            continue;
        }

        break;
    }

    Ok(lhs)
}
```

### Parsing Range Slicing and Null-Coalescing
Consider the expression:
```csharp
var slice = buffer[offset..(offset + length)] ?? defaultSlice;
```

The Pratt parser resolves this unambiguously:
1. `buffer` is parsed as the primary atom.
2. `[` triggers postfix indexing, evaluating `offset..(offset + length)`.
3. Inside `[ ... ]`, `DotDot` (`..`) binds with precedence `(19, 20)`, whereas `+` binds with `(21, 22)`. The parser correctly associates `(offset + length)` before completing the range.
4. The null-coalesce `??` with lower precedence `(3, 4)` captures the entire indexing expression on the left and `defaultSlice` on the right.

---

## 4. Multi-Pass AST Design: The Decoration Slot Pattern

In academic compilers, it is common to create distinct AST data structures for each phase (e.g. `ParsedAst` &rarr; `ResolvedAst` &rarr; `TypedAst` &rarr; `BorrowAst`). However, in a high-performance systems compiler, allocating and cloning separate AST trees incurs severe memory pressure and cache-miss overhead.

RustSharp utilizes the **Interior Decoration Slot Pattern**. The AST is parsed once and decorated in place across subsequent passes:

```rust
#[derive(Clone, Debug)]
pub enum Expr {
    Binary {
        op: BinaryOp,
        lhs: Box<Expr>,
        rhs: Box<Expr>,
        inferred_type: Option<TypeRef>, // Populated in Pass 2
    },
    MethodCall {
        target: Box<Expr>,
        method_name: String,
        args: Vec<CallArg>,
        inferred_target_type: Option<TypeRef>, // Populated in Pass 2
        inferred_borrow: Option<BorrowMode>,   // Populated in Pass 2.5
    },
    // ...
}
```

### Evolution of an AST Node Across Passes

```mermaid
sequenceDiagram
    participant Lex as Lexer & Parser (Pass 1)
    participant Sem as Symbol Resolver (Pass 2)
    participant Bor as Borrow Inferencer (Pass 2.5)
    participant Emi as Rust Emitter (Pass 3)

    Lex->>Sem: MethodCall { method_name: "Add", inferred_target_type: None, inferred_borrow: None }
    Note over Sem: Looks up GlobalSymbolTable<br/>Resolves target as OrderList
    Sem->>Bor: MethodCall { inferred_target_type: Some(OrderList), inferred_borrow: None }
    Note over Bor: Mutation Analysis determines Add()<br/>mutates self.items
    Bor->>Emi: MethodCall { inferred_borrow: Some(BorrowMode::MutBorrow) }
    Note over Emi: Emits native call:<br/>order_list.add(&mut item)
```

By retaining the same AST structure across Passes 1, 2, 2.5, and 3:
- We achieve compiler throughput exceeding **100,000 lines per second**.
- Node spans (`SourceSpan`) remain intact, enabling precision error diagnostics and bidirectional source mapping.

---

## 5. Summary & What's Next

By building our own UTF-8 lexer and Pratt expression parser using pure `std` Rust:
- We eliminate bloated parser-generator dependencies.
- We handle modern C# syntax seamlessly with zero runtime cost.
- We produce an extensible, decorate-in-place AST ready for multi-file semantic analysis.

In **[Blog 03: Virtual Namespaces — Freeing Code from the Physical File System](03_virtual_namespaces_freeing_code_from_files.md)**, we examine how RustSharp decouples source files from physical directory structures to solve one of the biggest ergonomic hurdles in systems programming.

