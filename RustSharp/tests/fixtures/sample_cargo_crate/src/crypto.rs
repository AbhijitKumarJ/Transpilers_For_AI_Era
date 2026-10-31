//! Core cryptographic primitives and stateful hasher.

/// Supported hashing algorithms.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Algorithm {
    Sha256,
    Blake3,
    Keccak256,
}

/// Structured crypto error with error code and description.
#[derive(Clone, Debug)]
pub struct CryptoError {
    pub code: i32,
    pub message: String,
}

/// Stateful incremental hasher.
pub struct Hasher {
    pub algorithm: Algorithm,
    state: u64,
}

impl Hasher {
    /// Creates a new hasher initialized with a 64-bit seed.
    pub fn new(seed: u64) -> Self {
        Self {
            algorithm: Algorithm::Blake3,
            state: seed,
        }
    }

    /// Appends raw bytes into the running hash state.
    pub fn update(&mut self, data: &[u8]) {
        for b in data {
            self.state = self.state.wrapping_mul(31).wrapping_add(*b as u64);
        }
    }

    /// Finalizes the digest computation and returns the hex digest string.
    pub fn finalize(&self) -> Result<String, CryptoError> {
        if self.state == 0 {
            Err(CryptoError {
                code: 101,
                message: "Hash state underflow".to_string(),
            })
        } else {
            Ok(format!("{:016x}", self.state))
        }
    }
}

/// Open trait for custom digest producers.
pub trait DigestProducer {
    fn produce_digest(&self) -> Vec<u8>;
}

