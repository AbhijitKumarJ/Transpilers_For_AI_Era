//! JSON-RPC 2.0 framing and transport for `rsharpc lsp`.
//!
//! Implements Content-Length header framing over standard I/O with pure-Rust std types.

use std::io::{self, BufRead, Write};

#[derive(Clone, Debug, PartialEq)]
pub struct JsonRpcMessage {
    pub jsonrpc: String,
    pub id: Option<String>,
    pub method: Option<String>,
    pub params: Option<String>,
    pub result: Option<String>,
    pub error: Option<String>,
}

impl JsonRpcMessage {
    pub fn new_response(id: &str, result_json: &str) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id: Some(id.to_string()),
            method: None,
            params: None,
            result: Some(result_json.to_string()),
            error: None,
        }
    }

    pub fn new_notification(method: &str, params_json: &str) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id: None,
            method: Some(method.to_string()),
            params: Some(params_json.to_string()),
            result: None,
            error: None,
        }
    }

    pub fn to_json(&self) -> String {
        let mut parts = vec!["\"jsonrpc\":\"2.0\"".to_string()];

        if let Some(id) = &self.id {
            parts.push(format!("\"id\":{}", id));
        }
        if let Some(m) = &self.method {
            parts.push(format!("\"method\":\"{}\"", m));
        }
        if let Some(p) = &self.params {
            parts.push(format!("\"params\":{}", p));
        }
        if let Some(r) = &self.result {
            parts.push(format!("\"result\":{}", r));
        }
        if let Some(e) = &self.error {
            parts.push(format!("\"error\":{}", e));
        }

        format!("{{{}}}", parts.join(","))
    }

    pub fn parse(raw: &str) -> Option<Self> {
        let trimmed = raw.trim();
        if !trimmed.starts_with('{') || !trimmed.ends_with('}') {
            return None;
        }

        let inner = &trimmed[1..trimmed.len() - 1];

        let id = extract_json_field(inner, "id");
        let method = extract_json_string_field(inner, "method");
        let params = extract_json_object_or_array(inner, "params");
        let result = extract_json_object_or_array(inner, "result");
        let error = extract_json_object_or_array(inner, "error");

        Some(Self {
            jsonrpc: "2.0".to_string(),
            id,
            method,
            params,
            result,
            error,
        })
    }
}

pub struct JsonRpcTransport;

impl JsonRpcTransport {
    /// Reads a single Content-Length prefixed JSON-RPC message from a buffered reader.
    pub fn read_message<R: BufRead>(reader: &mut R) -> io::Result<Option<JsonRpcMessage>> {
        let mut content_length: Option<usize> = None;

        loop {
            let mut line = String::new();
            let bytes_read = reader.read_line(&mut line)?;
            if bytes_read == 0 {
                return Ok(None); // EOF
            }

            let trimmed = line.trim();
            if trimmed.is_empty() {
                // Header-body separator reached
                break;
            }

            if let Some(val) = trimmed.strip_prefix("Content-Length:") {
                if let Ok(len) = val.trim().parse::<usize>() {
                    content_length = Some(len);
                }
            }
        }

        let length = match content_length {
            Some(l) => l,
            None => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "Missing Content-Length header in JSON-RPC stream.",
                ))
            }
        };

        let mut body_bytes = vec![0u8; length];
        reader.read_exact(&mut body_bytes)?;

        let body_str = String::from_utf8(body_bytes)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;

        Ok(JsonRpcMessage::parse(&body_str))
    }

    /// Writes a Content-Length prefixed JSON-RPC message to an output writer.
    pub fn write_message<W: Write>(writer: &mut W, msg: &JsonRpcMessage) -> io::Result<()> {
        let payload = msg.to_json();
        let header = format!("Content-Length: {}\r\n\r\n", payload.len());
        writer.write_all(header.as_bytes())?;
        writer.write_all(payload.as_bytes())?;
        writer.flush()?;
        Ok(())
    }
}

pub fn escape_json(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

pub fn unescape_json(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut chars = s.chars();
    while let Some(c) = chars.next() {
        if c == '\\' {
            match chars.next() {
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('t') => out.push('\t'),
                Some('\"') => out.push('\"'),
                Some('\\') => out.push('\\'),
                Some(other) => {
                    out.push('\\');
                    out.push(other);
                }
                None => out.push('\\'),
            }
        } else {
            out.push(c);
        }
    }
    out
}

pub fn extract_json_string_field(json: &str, field: &str) -> Option<String> {
    let pattern = format!("\"{}\":\"", field);
    let start = json.find(&pattern)? + pattern.len();
    let rest = &json[start..];
    let mut escaped = false;
    let mut end = None;
    for (i, c) in rest.char_indices() {
        if escaped {
            escaped = false;
        } else if c == '\\' {
            escaped = true;
        } else if c == '"' {
            end = Some(i);
            break;
        }
    }
    let end_idx = end?;
    Some(unescape_json(&rest[..end_idx]))
}

pub fn extract_json_field(json: &str, field: &str) -> Option<String> {
    let pattern = format!("\"{}\":", field);
    let start = json.find(&pattern)? + pattern.len();
    let rest = json[start..].trim_start();
    if let Some(inner) = rest.strip_prefix('"') {
        let mut escaped = false;
        let mut end = None;
        for (i, c) in inner.char_indices() {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                end = Some(i);
                break;
            }
        }
        let end_idx = end?;
        Some(format!("\"{}\"", unescape_json(&inner[..end_idx])))
    } else {
        let end = rest.find([',', '}']).unwrap_or(rest.len());
        Some(rest[..end].trim().to_string())
    }
}

pub fn extract_json_object_or_array(json: &str, field: &str) -> Option<String> {
    let pattern = format!("\"{}\":", field);
    let start = json.find(&pattern)? + pattern.len();
    let rest = json[start..].trim_start();

    if rest.starts_with('{') {
        let mut depth = 0;
        for (i, c) in rest.char_indices() {
            if c == '{' {
                depth += 1;
            } else if c == '}' {
                depth -= 1;
                if depth == 0 {
                    return Some(rest[..=i].to_string());
                }
            }
        }
    } else if rest.starts_with('[') {
        let mut depth = 0;
        for (i, c) in rest.char_indices() {
            if c == '[' {
                depth += 1;
            } else if c == ']' {
                depth -= 1;
                if depth == 0 {
                    return Some(rest[..=i].to_string());
                }
            }
        }
    } else if let Some(inner) = rest.strip_prefix('"') {
        let end = inner.find('"')?;
        return Some(format!("\"{}\"", &inner[..end]));
    } else {
        let end = rest.find([',', '}']).unwrap_or(rest.len());
        return Some(rest[..end].trim().to_string());
    }

    None
}
