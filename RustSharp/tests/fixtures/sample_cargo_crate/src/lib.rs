//! High performance crypto hashing library.

pub mod crypto;

/// Computes quick hash of a string slice using default algorithm.
pub fn quick_hash(input: &str) -> Result<String, crypto::CryptoError> {
    let mut h = crypto::Hasher::new(42);
    h.update(input.as_bytes());
    h.finalize()
}

pub const MAX_KEY_SIZE: usize = 256;

