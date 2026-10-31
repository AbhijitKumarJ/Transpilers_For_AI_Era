//! Rust source code tokenizer and declaration parser for `rsharp-bindgen`.
//!
//! Parses public Rust items (`pub struct`, `pub enum`, `pub fn`, `pub trait`,
//! `impl Type`, `pub const`) from source code without external dependencies.

use crate::bindgen::rs_ast::*;

#[derive(Clone, Debug, PartialEq)]
pub enum RsTokenKind {
    Ident(String),
    DocComment(String),
    ModDocComment(String),
    Keyword(String),
    Punct(char),
    DoubleColon,
    Arrow, // ->
    StringLiteral(String),
    NumberLiteral(String),
    Eof,
}

#[derive(Clone, Debug)]
pub struct RsToken {
    pub kind: RsTokenKind,
}

pub struct RsLexer {
    chars: Vec<char>,
    pos: usize,
}

impl RsLexer {
    pub fn new(src: &str) -> Self {
        Self {
            chars: src.chars().collect(),
            pos: 0,
        }
    }

    fn peek(&self, offset: usize) -> Option<char> {
        self.chars.get(self.pos + offset).copied()
    }

    pub fn tokenize(&mut self) -> Vec<RsToken> {
        let mut tokens = Vec::new();
        while self.pos < self.chars.len() {
            let ch = self.chars[self.pos];

            // Whitespace
            if ch.is_whitespace() {
                self.pos += 1;
                continue;
            }

            // Comments
            if ch == '/' {
                if self.peek(1) == Some('/') {
                    // Line comment or doc comment
                    if self.peek(2) == Some('/') && self.peek(3) != Some('/') {
                        // `///` outer doc comment
                        self.pos += 3;
                        let start = self.pos;
                        while self.pos < self.chars.len() && self.chars[self.pos] != '\n' {
                            self.pos += 1;
                        }
                        let doc: String = self.chars[start..self.pos].iter().collect();
                        tokens.push(RsToken {
                            kind: RsTokenKind::DocComment(doc.trim().to_string()),
                        });
                        continue;
                    } else if self.peek(2) == Some('!') {
                        // `//!` inner module doc comment
                        self.pos += 3;
                        let start = self.pos;
                        while self.pos < self.chars.len() && self.chars[self.pos] != '\n' {
                            self.pos += 1;
                        }
                        let doc: String = self.chars[start..self.pos].iter().collect();
                        tokens.push(RsToken {
                            kind: RsTokenKind::ModDocComment(doc.trim().to_string()),
                        });
                        continue;
                    } else {
                        // Regular line comment `//`
                        while self.pos < self.chars.len() && self.chars[self.pos] != '\n' {
                            self.pos += 1;
                        }
                        continue;
                    }
                } else if self.peek(1) == Some('*') {
                    // Block comment `/* ... */`
                    self.pos += 2;
                    while self.pos + 1 < self.chars.len() {
                        if self.chars[self.pos] == '*' && self.chars[self.pos + 1] == '/' {
                            self.pos += 2;
                            break;
                        }
                        self.pos += 1;
                    }
                    continue;
                }
            }

            // Attributes: `#[...]` or `#![...]`
            if ch == '#' {
                self.pos += 1;
                if self.pos < self.chars.len() && self.chars[self.pos] == '!' {
                    self.pos += 1;
                }
                if self.pos < self.chars.len() && self.chars[self.pos] == '[' {
                    self.pos += 1;
                    let mut depth = 1;
                    while self.pos < self.chars.len() && depth > 0 {
                        if self.chars[self.pos] == '[' {
                            depth += 1;
                        } else if self.chars[self.pos] == ']' {
                            depth -= 1;
                        }
                        self.pos += 1;
                    }
                    continue;
                }
            }

            // String literals
            if ch == '"' {
                self.pos += 1;
                let start = self.pos;
                let mut escaped = false;
                while self.pos < self.chars.len() {
                    let c = self.chars[self.pos];
                    if escaped {
                        escaped = false;
                    } else if c == '\\' {
                        escaped = true;
                    } else if c == '"' {
                        break;
                    }
                    self.pos += 1;
                }
                let s: String = self.chars[start..self.pos].iter().collect();
                if self.pos < self.chars.len() {
                    self.pos += 1; // consume closing '"'
                }
                tokens.push(RsToken {
                    kind: RsTokenKind::StringLiteral(s),
                });
                continue;
            }

            // Multi-char punctuation
            if ch == ':' && self.peek(1) == Some(':') {
                self.pos += 2;
                tokens.push(RsToken {
                    kind: RsTokenKind::DoubleColon,
                });
                continue;
            }
            if ch == '-' && self.peek(1) == Some('>') {
                self.pos += 2;
                tokens.push(RsToken {
                    kind: RsTokenKind::Arrow,
                });
                continue;
            }

            // Lifetime tokens `'a` -> skip lifetime annotations
            if ch == '\'' && self.peek(1).is_some_and(|c| c.is_alphabetic() || c == '_') {
                self.pos += 1;
                while self.pos < self.chars.len()
                    && (self.chars[self.pos].is_alphanumeric() || self.chars[self.pos] == '_')
                {
                    self.pos += 1;
                }
                continue;
            }

            // Numbers
            if ch.is_ascii_digit() {
                let start = self.pos;
                while self.pos < self.chars.len()
                    && (self.chars[self.pos].is_alphanumeric() || self.chars[self.pos] == '.')
                {
                    self.pos += 1;
                }
                let num: String = self.chars[start..self.pos].iter().collect();
                tokens.push(RsToken {
                    kind: RsTokenKind::NumberLiteral(num),
                });
                continue;
            }

            // Identifiers and Keywords
            if ch.is_alphabetic() || ch == '_' {
                let start = self.pos;
                while self.pos < self.chars.len()
                    && (self.chars[self.pos].is_alphanumeric() || self.chars[self.pos] == '_')
                {
                    self.pos += 1;
                }
                let id: String = self.chars[start..self.pos].iter().collect();
                match id.as_str() {
                    "pub" | "crate" | "struct" | "enum" | "fn" | "trait" | "impl" | "type"
                    | "const" | "mut" | "ref" | "self" | "Self" | "for" | "mod" | "as"
                    | "where" | "async" | "unsafe" | "extern" => {
                        tokens.push(RsToken {
                            kind: RsTokenKind::Keyword(id),
                        });
                    }
                    _ => {
                        tokens.push(RsToken {
                            kind: RsTokenKind::Ident(id),
                        });
                    }
                }
                continue;
            }

            // Single char punctuation
            self.pos += 1;
            tokens.push(RsToken {
                kind: RsTokenKind::Punct(ch),
            });
        }

        tokens.push(RsToken {
            kind: RsTokenKind::Eof,
        });
        tokens
    }
}

pub struct RsParser {
    tokens: Vec<RsToken>,
    pos: usize,
}

impl RsParser {
    pub fn new(tokens: Vec<RsToken>) -> Self {
        Self { tokens, pos: 0 }
    }

    fn peek(&self, offset: usize) -> &RsTokenKind {
        self.tokens
            .get(self.pos + offset)
            .map(|t| &t.kind)
            .unwrap_or(&RsTokenKind::Eof)
    }

    fn advance(&mut self) -> &RsTokenKind {
        let idx = self.pos;
        if self.pos < self.tokens.len() {
            self.pos += 1;
        }
        &self.tokens[idx].kind
    }

    fn match_keyword(&mut self, kw: &str) -> bool {
        if let RsTokenKind::Keyword(s) = self.peek(0) {
            if s == kw {
                self.advance();
                return true;
            }
        }
        false
    }

    fn match_punct(&mut self, ch: char) -> bool {
        if let RsTokenKind::Punct(c) = self.peek(0) {
            if *c == ch {
                self.advance();
                return true;
            }
        }
        false
    }

    fn match_double_colon(&mut self) -> bool {
        if let RsTokenKind::DoubleColon = self.peek(0) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn match_arrow(&mut self) -> bool {
        if let RsTokenKind::Arrow = self.peek(0) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn expect_ident(&mut self) -> Option<String> {
        match self.peek(0) {
            RsTokenKind::Ident(s) => {
                let res = s.clone();
                self.advance();
                Some(res)
            }
            RsTokenKind::Keyword(s) if s == "self" || s == "Self" => {
                let res = s.clone();
                self.advance();
                Some(res)
            }
            _ => None,
        }
    }

    fn skip_balanced_braces(&mut self) {
        if self.match_punct('{') {
            let mut depth = 1;
            while depth > 0 && self.peek(0) != &RsTokenKind::Eof {
                match self.advance() {
                    RsTokenKind::Punct('{') => depth += 1,
                    RsTokenKind::Punct('}') => depth -= 1,
                    _ => {}
                }
            }
        }
    }

    fn skip_until_semicolon_or_brace(&mut self) {
        while self.peek(0) != &RsTokenKind::Eof {
            if self.match_punct(';') {
                break;
            }
            if let RsTokenKind::Punct('{') = self.peek(0) {
                self.skip_balanced_braces();
                break;
            }
            self.advance();
        }
    }

    pub fn parse_module(&mut self, module_name: &str) -> RustModule {
        let mut module = RustModule {
            name: module_name.to_string(),
            ..Default::default()
        };

        let mut pending_docs: Vec<String> = Vec::new();

        while self.peek(0) != &RsTokenKind::Eof {
            // Inner doc comments `//!`
            if let RsTokenKind::ModDocComment(doc) = self.peek(0) {
                module.doc_comments.push(doc.clone());
                self.advance();
                continue;
            }

            // Outer doc comments `///`
            if let RsTokenKind::DocComment(doc) = self.peek(0) {
                pending_docs.push(doc.clone());
                self.advance();
                continue;
            }

            // Visibility modifier `pub` or `pub(...)`
            let mut is_pub = false;
            if self.match_keyword("pub") {
                is_pub = true;
                if self.match_punct('(') {
                    // `pub(crate)`, `pub(super)`, etc.
                    while self.peek(0) != &RsTokenKind::Eof && !self.match_punct(')') {
                        self.advance();
                    }
                }
            }

            // Modifiers: `async`, `unsafe`, `extern`
            while self.match_keyword("async")
                || self.match_keyword("unsafe")
                || self.match_keyword("extern")
            {
                if self.match_punct('\"') {
                    self.advance();
                }
            }

            match self.peek(0) {
                RsTokenKind::Keyword(kw) if kw == "struct" => {
                    self.advance();
                    if let Some(st) = self.parse_struct(is_pub, std::mem::take(&mut pending_docs)) {
                        module.structs.push(st);
                    }
                }
                RsTokenKind::Keyword(kw) if kw == "enum" => {
                    self.advance();
                    if let Some(en) = self.parse_enum(is_pub, std::mem::take(&mut pending_docs)) {
                        module.enums.push(en);
                    }
                }
                RsTokenKind::Keyword(kw) if kw == "trait" => {
                    self.advance();
                    if let Some(tr) = self.parse_trait(is_pub, std::mem::take(&mut pending_docs)) {
                        module.traits.push(tr);
                    }
                }
                RsTokenKind::Keyword(kw) if kw == "fn" => {
                    self.advance();
                    if let Some(f) = self.parse_fn(is_pub, std::mem::take(&mut pending_docs)) {
                        module.functions.push(f);
                    }
                }
                RsTokenKind::Keyword(kw) if kw == "impl" => {
                    self.advance();
                    pending_docs.clear();
                    if let Some(im) = self.parse_impl() {
                        module.impls.push(im);
                    }
                }
                RsTokenKind::Keyword(kw) if kw == "const" => {
                    self.advance();
                    if let Some(cn) = self.parse_const(is_pub, std::mem::take(&mut pending_docs)) {
                        module.consts.push(cn);
                    }
                }
                RsTokenKind::Keyword(kw) if kw == "mod" => {
                    self.advance();
                    if let Some(mod_name) = self.expect_ident() {
                        if self.match_punct(';') {
                            // Submodule declared via `mod foo;` — caller will discover on disk
                            let sub = RustModule {
                                name: mod_name,
                                ..Default::default()
                            };
                            if is_pub {
                                module.submodules.push(sub);
                            }
                        } else if self.match_punct('{') {
                            // Inline submodule `mod foo { ... }`
                            let sub = self.parse_module(&mod_name);
                            self.match_punct('}');
                            if is_pub {
                                module.submodules.push(sub);
                            }
                        }
                    }
                    pending_docs.clear();
                }
                _ => {
                    pending_docs.clear();
                    self.advance();
                }
            }
        }

        module
    }

    fn parse_generics(&mut self) -> Vec<String> {
        let mut generics = Vec::new();
        if self.match_punct('<') {
            let mut depth = 1;
            while depth > 0 && self.peek(0) != &RsTokenKind::Eof {
                if let RsTokenKind::Ident(s) = self.peek(0) {
                    if depth == 1 {
                        generics.push(s.clone());
                    }
                }
                if self.match_punct('<') {
                    depth += 1;
                } else if self.match_punct('>') {
                    depth -= 1;
                } else {
                    self.advance();
                }
            }
        }
        generics
    }

    fn parse_struct(&mut self, is_pub: bool, doc_comments: Vec<String>) -> Option<RustStruct> {
        let name = self.expect_ident()?;
        let generics = self.parse_generics();

        let mut fields = Vec::new();

        if self.match_punct('{') {
            // Named fields `struct Foo { pub a: i32, b: String }`
            let mut pending_field_docs = Vec::new();
            while !self.match_punct('}') && self.peek(0) != &RsTokenKind::Eof {
                if let RsTokenKind::DocComment(d) = self.peek(0) {
                    pending_field_docs.push(d.clone());
                    self.advance();
                    continue;
                }

                let mut field_pub = false;
                if self.match_keyword("pub") {
                    field_pub = true;
                    if self.match_punct('(') {
                        while self.peek(0) != &RsTokenKind::Eof && !self.match_punct(')') {
                            self.advance();
                        }
                    }
                }

                if let Some(field_name) = self.expect_ident() {
                    if self.match_punct(':') {
                        let ty = self.parse_type();
                        fields.push(RustField {
                            name: field_name,
                            doc_comments: std::mem::take(&mut pending_field_docs),
                            is_pub: field_pub,
                            ty,
                        });
                        self.match_punct(',');
                    }
                } else {
                    self.advance();
                }
            }
        } else if self.match_punct('(') {
            // Tuple struct `struct Seconds(pub u32);`
            let mut idx = 0;
            while !self.match_punct(')') && self.peek(0) != &RsTokenKind::Eof {
                let mut field_pub = false;
                if self.match_keyword("pub") {
                    field_pub = true;
                    if self.match_punct('(') {
                        while self.peek(0) != &RsTokenKind::Eof && !self.match_punct(')') {
                            self.advance();
                        }
                    }
                }
                let ty = self.parse_type();
                fields.push(RustField {
                    name: format!("item{}", idx),
                    doc_comments: Vec::new(),
                    is_pub: field_pub,
                    ty,
                });
                idx += 1;
                self.match_punct(',');
            }
            self.match_punct(';');
        } else if self.match_punct(';') {
            // Unit struct `struct Empty;`
        }

        Some(RustStruct {
            name,
            doc_comments,
            is_pub,
            generics,
            fields,
        })
    }

    fn parse_enum(&mut self, is_pub: bool, doc_comments: Vec<String>) -> Option<RustEnum> {
        let name = self.expect_ident()?;
        let generics = self.parse_generics();

        let mut variants = Vec::new();

        if self.match_punct('{') {
            let mut pending_variant_docs = Vec::new();
            while !self.match_punct('}') && self.peek(0) != &RsTokenKind::Eof {
                if let RsTokenKind::DocComment(d) = self.peek(0) {
                    pending_variant_docs.push(d.clone());
                    self.advance();
                    continue;
                }

                if let Some(variant_name) = self.expect_ident() {
                    let mut payload = Vec::new();
                    if self.match_punct('(') {
                        // Tuple variant `Status(i32, String)`
                        while !self.match_punct(')') && self.peek(0) != &RsTokenKind::Eof {
                            payload.push(self.parse_type());
                            self.match_punct(',');
                        }
                    } else if self.match_punct('{') {
                        // Struct variant -> skip internals for simple enum mapping
                        while !self.match_punct('}') && self.peek(0) != &RsTokenKind::Eof {
                            self.advance();
                        }
                    }

                    // Skip explicit discriminator `= 1`
                    if self.match_punct('=') {
                        while self.peek(0) != &RsTokenKind::Eof
                            && self.peek(0) != &RsTokenKind::Punct(',')
                            && self.peek(0) != &RsTokenKind::Punct('}')
                        {
                            self.advance();
                        }
                    }

                    variants.push(RustEnumVariant {
                        name: variant_name,
                        doc_comments: std::mem::take(&mut pending_variant_docs),
                        payload,
                    });
                    self.match_punct(',');
                } else {
                    self.advance();
                }
            }
        }

        Some(RustEnum {
            name,
            doc_comments,
            is_pub,
            generics,
            variants,
        })
    }

    fn parse_trait(&mut self, is_pub: bool, doc_comments: Vec<String>) -> Option<RustTrait> {
        let name = self.expect_ident()?;
        let _generics = self.parse_generics();

        let mut methods = Vec::new();

        if self.match_punct('{') {
            let mut pending_fn_docs = Vec::new();
            while !self.match_punct('}') && self.peek(0) != &RsTokenKind::Eof {
                if let RsTokenKind::DocComment(d) = self.peek(0) {
                    pending_fn_docs.push(d.clone());
                    self.advance();
                    continue;
                }

                if self.match_keyword("fn") {
                    if let Some(f) = self.parse_fn(true, std::mem::take(&mut pending_fn_docs)) {
                        methods.push(f);
                    }
                } else {
                    self.advance();
                }
            }
        }

        Some(RustTrait {
            name,
            doc_comments,
            is_pub,
            methods,
        })
    }

    fn parse_impl(&mut self) -> Option<RustImpl> {
        // `impl<T> StructName<T> { ... }` or `impl Trait for StructName { ... }`
        let _generics = self.parse_generics();

        let first_name = self.expect_ident()?;
        let _first_generics = self.parse_generics();

        let (target_type, trait_name) = if self.match_keyword("for") {
            let target = self.expect_ident()?;
            let _target_generics = self.parse_generics();
            (target, Some(first_name))
        } else {
            (first_name, None)
        };

        let mut methods = Vec::new();

        if self.match_punct('{') {
            let mut pending_fn_docs = Vec::new();
            while !self.match_punct('}') && self.peek(0) != &RsTokenKind::Eof {
                if let RsTokenKind::DocComment(d) = self.peek(0) {
                    pending_fn_docs.push(d.clone());
                    self.advance();
                    continue;
                }

                let mut is_pub = false;
                if self.match_keyword("pub") {
                    is_pub = true;
                    if self.match_punct('(') {
                        while self.peek(0) != &RsTokenKind::Eof && !self.match_punct(')') {
                            self.advance();
                        }
                    }
                }

                if self.match_keyword("fn") {
                    if let Some(f) = self.parse_fn(is_pub, std::mem::take(&mut pending_fn_docs)) {
                        methods.push(f);
                    }
                } else {
                    self.advance();
                }
            }
        }

        Some(RustImpl {
            target_type,
            trait_name,
            methods,
        })
    }

    fn parse_fn(&mut self, is_pub: bool, doc_comments: Vec<String>) -> Option<RustFn> {
        let name = self.expect_ident()?;
        let _generics = self.parse_generics();

        let mut self_receiver = None;
        let mut params = Vec::new();

        if self.match_punct('(') {
            // Check self receiver
            if self.match_punct('&') {
                if self.match_keyword("mut") {
                    if self.match_keyword("self") {
                        self_receiver = Some(RustSelfReceiver::MutRef);
                        self.match_punct(',');
                    }
                } else if self.match_keyword("self") {
                    self_receiver = Some(RustSelfReceiver::Ref);
                    self.match_punct(',');
                }
            } else if self.match_keyword("self") {
                self_receiver = Some(RustSelfReceiver::Value);
                self.match_punct(',');
            }

            // Normal parameters
            while !self.match_punct(')') && self.peek(0) != &RsTokenKind::Eof {
                let mut is_mut = false;
                if self.match_keyword("mut") {
                    is_mut = true;
                }
                if let Some(param_name) = self.expect_ident() {
                    if self.match_punct(':') {
                        let ty = self.parse_type();
                        params.push(RustParam {
                            name: if is_mut {
                                format!("mut_{}", param_name)
                            } else {
                                param_name
                            },
                            ty,
                        });
                        self.match_punct(',');
                    }
                } else {
                    self.advance();
                }
            }
        }

        // Return type `-> Type`
        let return_type = if self.match_arrow() {
            self.parse_type()
        } else {
            RustType::Unit
        };

        // Skip body `{ ... }` or `;`
        if self.match_punct(';') {
            // signature only (e.g. in trait)
        } else if self.peek(0) == &RsTokenKind::Punct('{') {
            self.skip_balanced_braces();
        }

        Some(RustFn {
            name,
            doc_comments,
            is_pub,
            self_receiver,
            params,
            return_type,
        })
    }

    fn parse_const(&mut self, is_pub: bool, doc_comments: Vec<String>) -> Option<RustConst> {
        let name = self.expect_ident()?;
        if !self.match_punct(':') {
            self.skip_until_semicolon_or_brace();
            return None;
        }
        let ty = self.parse_type();
        let mut val_tokens = Vec::new();
        if self.match_punct('=') {
            while self.peek(0) != &RsTokenKind::Eof && !self.match_punct(';') {
                match self.advance() {
                    RsTokenKind::Ident(s) | RsTokenKind::Keyword(s) => val_tokens.push(s.clone()),
                    RsTokenKind::NumberLiteral(n) | RsTokenKind::StringLiteral(n) => {
                        val_tokens.push(n.clone())
                    }
                    RsTokenKind::Punct(c) => val_tokens.push(c.to_string()),
                    _ => {}
                }
            }
        }
        Some(RustConst {
            name,
            doc_comments,
            is_pub,
            ty,
            value: val_tokens.join(" "),
        })
    }

    pub fn parse_type(&mut self) -> RustType {
        // Reference: `&'a str`, `&mut [u8]`, `&T`
        if self.match_punct('&') {
            let is_mut = self.match_keyword("mut");
            let inner = self.parse_type();
            return RustType::Reference {
                is_mut,
                inner: Box::new(inner),
            };
        }

        // Slice / Array: `[T]` or `[T; N]`
        if self.match_punct('[') {
            let inner = self.parse_type();
            // Skip `; N` if fixed array
            if self.match_punct(';') {
                while !self.match_punct(']') && self.peek(0) != &RsTokenKind::Eof {
                    self.advance();
                }
            } else {
                self.match_punct(']');
            }
            return RustType::Slice {
                is_mut: false,
                inner: Box::new(inner),
            };
        }

        // Tuple: `(A, B)` or Unit `()`
        if self.match_punct('(') {
            if self.match_punct(')') {
                return RustType::Unit;
            }
            let mut elems = Vec::new();
            while !self.match_punct(')') && self.peek(0) != &RsTokenKind::Eof {
                elems.push(self.parse_type());
                self.match_punct(',');
            }
            if elems.len() == 1 {
                return elems.remove(0);
            }
            return RustType::Tuple(elems);
        }

        // Self keyword
        if let RsTokenKind::Keyword(kw) = self.peek(0) {
            if kw == "Self" {
                self.advance();
                return RustType::SelfType;
            }
        }

        // Named type / Path: `std::collections::HashMap<K, V>`
        let mut path = Vec::new();
        if let Some(id) = self.expect_ident() {
            path.push(id);
            while self.match_double_colon() {
                if let Some(sub) = self.expect_ident() {
                    path.push(sub);
                } else {
                    break;
                }
            }
        } else {
            return RustType::Unit;
        }

        let mut generic_args = Vec::new();
        if self.match_punct('<') {
            while !self.match_punct('>') && self.peek(0) != &RsTokenKind::Eof {
                generic_args.push(self.parse_type());
                self.match_punct(',');
            }
        }

        let simple_name = path.last().map(|s| s.as_str()).unwrap_or("");
        match simple_name {
            "i8" | "u8" | "i16" | "u16" | "i32" | "u32" | "i64" | "u64" | "isize" | "usize"
            | "f32" | "f64" | "bool" | "char" => RustType::Primitive(simple_name.to_string()),
            _ => RustType::Named { path, generic_args },
        }
    }
}
