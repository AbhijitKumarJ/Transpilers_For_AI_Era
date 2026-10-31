# RustSharp Diagnostics

| Field | Value |
| :--- | :--- |
| **Compiler Engine** | `DiagnosticEngine` (`src/diagnostics.rs`) |
| **Exit Codes** | `0` (Success), `1` (Errors Detected) |
| **Status** | Active |
| **Owner** | RustSharp Core Team |
| **Related Documents** | [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md), [TECH-STACK.md](TECH-STACK.md) |

---

## 1. Overview & Architectural Principles

The RustSharp diagnostic engine produces precise, user-friendly diagnostic messages that emulate `rustc` and modern compiler outputs. Every diagnostic is pinned to exact 1-indexed file, line, and column coordinates, renders a two-line visual ASCII caret context, and provides actionable remediation guidance.

### Principles
1. **Early Rejection:** Ownership violations, uncaught effects, and syntax errors are rejected at the `.rsharp` level before invalid Rust code is emitted.
2. **Actionable Remediation:** Every error includes an `= help:` suggestion showing how to refactor the C# code into borrow-checker-compliant form.
3. **Resilient Recovery:** The parser and type checker collect as many independent diagnostics as possible before halting compilation.

---

## 2. Diagnostic Output Format

```text
error[RSHARP001]: illegal shared mutability on 'order'
  --> src/Features/Checkout/OrderHandler.rsharp:106:14
   |
106 |     order.Total -= 10.0m;
   |     ^^^^^^^^^^^
   = help: 'order' is simultaneously borrowed as immutable by '_db.Save(order)'. Consider sequencing mutations or cloning.
```

- **Severity:** `error`, `warning`, `note`.
- **Code:** `RSHARPnnn` formatted diagnostic code.
- **Location:** `--> <file_path>:<line>:<col>`.
- **Visual Snippet:** Numbered source line with ASCII carets (`^^^^`) underlining the offending span.
- **Help Message:** Contextual fix recommendation.

---

## 3. Diagnostic Catalog

### `RSHARP000` - Syntax or Parse Error
- **Severity:** Error
- **Cause:** Input token stream does not conform to the RustSharp grammar (e.g. unclosed delimiter, missing semicolon, invalid token).
- **Trigger Example:**
  ```csharp
  public record Order(int Id decimal Total); // Missing comma
  ```
- **Diagnostic Output:**
  ```text
  error[RSHARP000]: unexpected token 'decimal', expected ',' or ')'
    --> src/Models.rsharp:1:28
     |
   1 | public record Order(int Id decimal Total);
     |                            ^^^^^^^
     = help: separate record parameters with commas.
  ```

---

### `RSHARP001` - Illegal Shared Mutability (Alias Mutation Conflict)
- **Severity:** Error
- **Cause:** A variable has an active mutable borrow while simultaneously being accessed immutably, or multiple mutable references exist in the same scope ($\text{Aliasing} \oplus \text{Mutability}$ violation).
- **Trigger Example:**
  ```csharp
  public void Process(Order order)
  {
      var reader = order;          // Immutable alias
      order.Total += 50.0m;        // Mutation while borrowed
      Console.WriteLine(reader.Total);
  }
  ```
- **Diagnostic Output:**
  ```text
  error[RSHARP001]: cannot mutate 'order' while borrowed immutably
    --> src/OrderProcessor.rsharp:4:5
     |
   4 |     order.Total += 50.0m;
     |     ^^^^^^^^^^^
     = help: 'reader' holds an active immutable borrow of 'order'. Perform mutations before taking borrows or clone the value.
  ```

---

### `RSHARP002` - Escaping Local Borrow / Lifetime Violation
- **Severity:** Error
- **Cause:** A reference to a stack-allocated variable is returned from a function or stored in a longer-lived data structure.
- **Trigger Example:**
  ```csharp
  public string GetSummary()
  {
      var localOrder = new Order(1, 100.0m, new List<string>());
      return localOrder.SummarizeRef(); // Returns reference to stack local
  }
  ```
- **Diagnostic Output:**
  ```text
  error[RSHARP002]: reference to local variable 'localOrder' escapes function scope
    --> src/OrderSummary.rsharp:4:12
     |
   4 |     return localOrder.SummarizeRef();
     |            ^^^^^^^^^^^^^^^^^^^^^^^^^
     = help: 'localOrder' will be dropped when the function returns. Return an owned 'string' instead of a borrowed reference.
  ```

---

### `RSHARP003` - Uncaught Checked Effect (Missing `throws`)
- **Severity:** Error
- **Cause:** A function invokes a callee that declares `throws E`, but neither handles the error via `try-catch` nor declares `throws E` in its own method signature.
- **Trigger Example:**
  ```csharp
  public static int ParseConfig(string raw)
  {
      return ParsePort(raw); // ParsePort declares 'throws ParseError'
  }
  ```
- **Diagnostic Output:**
  ```text
  error[RSHARP003]: uncaught checked effect 'ParseError' in method 'ParseConfig'
    --> src/Config.rsharp:3:12
     |
   3 |     return ParsePort(raw);
     |            ^^^^^^^^^^^^^^
     = help: declare 'throws ParseError' on 'ParseConfig' or wrap the invocation in a 'try { ... } catch (ParseError err) { ... }' block.
  ```

---

### `RSHARP004` - Type Mismatch or Unresolved Identifier
- **Severity:** Error
- **Cause:** An expression cannot be converted to the target type, or a referenced identifier (type, method, field) does not exist in the current scope.
- **Trigger Example:**
  ```csharp
  int count = "123";
  ```
- **Diagnostic Output:**
  ```text
  error[RSHARP004]: mismatched types: expected 'int', found 'string'
    --> src/App.rsharp:1:13
     |
   1 | int count = "123";
     |             ^^^^^
     = help: use 'int.Parse("123")' to convert string to integer.
  ```

---

### `RSHARP005` - Encapsulation or Visibility Violation
- **Severity:** Error
- **Cause:** Attempting to access a `private`, `protected`, or `internal` member from a scope that does not have authorization.
- **Trigger Example:**
  ```csharp
  var db = new Database();
  db._connectionString = "secret"; // _connectionString is private
  ```
- **Diagnostic Output:**
  ```text
  error[RSHARP005]: field '_connectionString' is private to 'Database'
    --> src/Main.rsharp:2:4
     |
   2 | db._connectionString = "secret";
     |    ^^^^^^^^^^^^^^^^^
     = help: private fields cannot be accessed outside their declaring type. Provide a public property or method.
  ```

