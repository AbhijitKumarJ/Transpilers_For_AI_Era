//! Rust Public Item Abstract Syntax Tree for `rsharp-bindgen`.
//!
//! Represents public declarations extracted from native Rust crates for translation
//! into ambient `.d.rsharp` header files.

#[derive(Clone, Debug, PartialEq)]
pub enum RustType {
    /// Primitive types: `i8`, `u8`, `i16`, `u16`, `i32`, `u32`, `i64`, `u64`, `isize`, `usize`, `f32`, `f64`, `bool`, `char`.
    Primitive(String),
    /// Named type: `String`, `Option<T>`, `Result<T, E>`, `Vec<T>`, `HashMap<K, V>`, custom structs/enums.
    Named {
        path: Vec<String>,
        generic_args: Vec<RustType>,
    },
    /// Borrowed reference: `&T` or `&mut T`.
    Reference { is_mut: bool, inner: Box<RustType> },
    /// Borrowed slice: `&[T]` or `&mut [T]`.
    Slice { is_mut: bool, inner: Box<RustType> },
    /// Tuples: `(A, B, C)`.
    Tuple(Vec<RustType>),
    /// Unit type `()`.
    Unit,
    /// `Self` reference in impl blocks.
    SelfType,
}

impl RustType {
    pub fn is_str(&self) -> bool {
        match self {
            RustType::Reference { inner, .. } => {
                matches!(&**inner, RustType::Named { path, .. } if path.last().map(|s| s.as_str()) == Some("str"))
            }
            RustType::Named { path, .. } => path.last().map(|s| s.as_str()) == Some("str"),
            _ => false,
        }
    }

    pub fn is_result(&self) -> bool {
        match self {
            RustType::Named { path, .. } => path.last().map(|s| s.as_str()) == Some("Result"),
            _ => false,
        }
    }

    pub fn is_option(&self) -> bool {
        match self {
            RustType::Named { path, .. } => path.last().map(|s| s.as_str()) == Some("Option"),
            _ => false,
        }
    }

    pub fn is_vec(&self) -> bool {
        match self {
            RustType::Named { path, .. } => path.last().map(|s| s.as_str()) == Some("Vec"),
            _ => false,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum RustSelfReceiver {
    /// `&self`
    Ref,
    /// `&mut self`
    MutRef,
    /// `self` (by value)
    Value,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustParam {
    pub name: String,
    pub ty: RustType,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustFn {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub is_pub: bool,
    pub self_receiver: Option<RustSelfReceiver>,
    pub params: Vec<RustParam>,
    pub return_type: RustType,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustField {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub is_pub: bool,
    pub ty: RustType,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustStruct {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub is_pub: bool,
    pub generics: Vec<String>,
    pub fields: Vec<RustField>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustEnumVariant {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub payload: Vec<RustType>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustEnum {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub is_pub: bool,
    pub generics: Vec<String>,
    pub variants: Vec<RustEnumVariant>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustTrait {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub is_pub: bool,
    pub methods: Vec<RustFn>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustImpl {
    pub target_type: String,
    pub trait_name: Option<String>,
    pub methods: Vec<RustFn>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RustConst {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub is_pub: bool,
    pub ty: RustType,
    pub value: String,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct RustModule {
    pub name: String,
    pub doc_comments: Vec<String>,
    pub structs: Vec<RustStruct>,
    pub enums: Vec<RustEnum>,
    pub traits: Vec<RustTrait>,
    pub functions: Vec<RustFn>,
    pub impls: Vec<RustImpl>,
    pub consts: Vec<RustConst>,
    pub submodules: Vec<RustModule>,
}
