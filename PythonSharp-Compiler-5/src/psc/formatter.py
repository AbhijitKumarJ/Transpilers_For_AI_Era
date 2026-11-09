from __future__ import annotations

import re

_GLOBAL_MASK_PATTERN = re.compile(
    r'(\$@"(?:""|[^"])*"'
    r'|@"(?:""|[^"])*"'
    r'|\$"(?:\\.|[^"\\])*"'
    r'|"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'"
    r"|/\*[\s\S]*?\*/"
    r"|//.*$)",
    re.MULTILINE,
)


def format_code(source: str, tab_size: int = 4, insert_spaces: bool = True) -> str:
    """
    Formats PythonSharp (.ps) source code:
    - Normalizes indentation based on braces and block structure (Allman style).
    - Preserves string literals and comments exactly across multiple lines.
    - Normalizes operator spacing, commas, and keyword parentheses.
    - Strips trailing whitespace and collapses excessive blank lines.
    """
    if not source.strip():
        return ""

    tokens: list[str] = []

    def repl(m: re.Match[str]) -> str:
        tokens.append(m.group(0))
        return f"__PS_FMT_TOK_{len(tokens) - 1}__"

    # Step 1: Mask all strings and comments globally
    masked_source = _GLOBAL_MASK_PATTERN.sub(repl, source)

    # Step 2: Split lines and preprocess brace positions
    # If a line ends with "{" (e.g. `class Foo {` or `if (x) {`) and doesn't close on the same line,
    # put "{" on its own line (Allman style).
    pre_lines: list[str] = []
    for raw in masked_source.splitlines():
        line = raw.strip()
        if not line:
            pre_lines.append("")
            continue

        # Check if line ends with "{" and has preceding content without a matching "}"
        if line.endswith("{") and len(line) > 1 and "}" not in line:
            pre_lines.append(line[:-1].rstrip())
            pre_lines.append("{")
        elif line.startswith("} catch") or line.startswith("} else") or line.startswith("} finally"):
            # Split "} else" -> "}" \n "else"
            parts = line.split(" ", 1)
            pre_lines.append("}")
            if parts[1].endswith("{") and len(parts[1]) > 1:
                pre_lines.append(parts[1][:-1].rstrip())
                pre_lines.append("{")
            else:
                pre_lines.append(parts[1])
        else:
            pre_lines.append(line)

    # Step 3: Insert blank line after namespace declaration and between using block and types
    processed_lines: list[str] = []
    in_using_block = False
    for i, line in enumerate(pre_lines):
        if not line:
            processed_lines.append("")
            continue

        # Namespace followed immediately by non-empty line
        if line.startswith("namespace ") and line.endswith(";"):
            processed_lines.append(line)
            if i + 1 < len(pre_lines) and pre_lines[i + 1]:
                processed_lines.append("")
            continue

        if line.startswith("using ") and line.endswith(";"):
            in_using_block = True
            processed_lines.append(line)
            # If next line is not using, add blank line
            if i + 1 < len(pre_lines) and pre_lines[i + 1] and not pre_lines[i + 1].startswith("using "):
                processed_lines.append("")
                in_using_block = False
            continue

        processed_lines.append(line)

    # Step 4: Indent and format line content
    indent_unit = " " * tab_size if insert_spaces else "\t"
    out_lines: list[str] = []
    indent_level = 0
    consecutive_empty = 0

    for raw_line in processed_lines:
        stripped = raw_line.strip()

        if not stripped:
            if consecutive_empty < 1 and out_lines:
                out_lines.append("")
                consecutive_empty += 1
            continue

        consecutive_empty = 0

        # Check leading closing delimiters to dedent current line
        leading_close_braces = 0
        for ch in stripped:
            if ch in ("}", "]", ")"):
                leading_close_braces += 1
            else:
                break

        is_switch_label = stripped.startswith("case ") or stripped.startswith("default:")

        current_indent = max(0, indent_level - leading_close_braces)
        if is_switch_label:
            current_indent = max(0, current_indent - 1)

        # Normalize line punctuation & spacing
        formatted_content = _format_line_tokens(stripped)

        out_lines.append(f"{indent_unit * current_indent}{formatted_content}")

        # Compute indent delta for next lines
        delta = stripped.count("{") - stripped.count("}")
        indent_level = max(0, indent_level + delta)

    result = "\n".join(out_lines).rstrip() + "\n"

    # Step 5: Restore masked tokens
    for idx, tok in enumerate(tokens):
        result = result.replace(f"__PS_FMT_TOK_{idx}__", tok)

    return result


def _format_line_tokens(line: str) -> str:
    code = line

    # 1. Normalise comma spacing
    code = re.sub(r"\s*,\s*", ", ", code)

    # 2. Normalise keyword paren
    code = re.sub(r"\b(if|for|foreach|while|switch|catch|using|lock)\s*\(", r"\1 (", code)

    # 3. Remove space before semicolon and ensure space after semicolon in for loops
    code = re.sub(r"\s+;", ";", code)
    code = re.sub(r";\s*(?=[^\s;\}\)])", "; ", code)

    # 4. Normalise compound and comparison operators
    code = re.sub(r"\s*(\+=|-=|\*=|/=|%=|=>|\?\?=|==|!=|<=|>=|\?\?|&&|\|\|)\s*", r" \1 ", code)

    # 5. Normalise single assignment '=' (excluding <=, >=, ==, !=, +=, etc.)
    code = re.sub(r"(?<![=!<>+\-*/&|%?])\s*=\s*(?![=><])", " = ", code)

    # 6. Relational < and > in for-loops, if, while conditions
    def _fix_comparisons(m: re.Match[str]) -> str:
        s = m.group(0)
        return re.sub(r"(?<=[a-z0-9_\)\]])\s*(<|>)\s*(?=[a-z0-9_\(\[])", r" \1 ", s)

    code = re.sub(r"\bfor\s*\([^)]+\)", _fix_comparisons, code)
    code = re.sub(r"\b(?:if|while)\s*\([^)]+\)", _fix_comparisons, code)

    # 7. Binary arithmetic (+, -, *, /) when surrounded by identifiers/numbers
    code = re.sub(r"([A-Za-z0-9_\)\]])\s*([+\-*/])\s*([A-Za-z0-9_\(\[])", r"\1 \2 \3", code)

    return code
