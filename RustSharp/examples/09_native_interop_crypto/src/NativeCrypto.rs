use super::NativeCrypto;

impl NativeCrypto {
    pub fn murmur_hash3(mut k: u32, seed: u32) -> u32 {
        k = k.wrapping_mul(0xcc9e2d51);
        k = k.rotate_left(15);
        k = k.wrapping_mul(0x1b873593);

        let mut h = seed ^ k;
        h = h.rotate_left(13);
        h = h.wrapping_mul(5).wrapping_add(0xe6546b64);
        h ^= 4;
        h ^= h >> 16;
        h = h.wrapping_mul(0x85ebca6b);
        h ^= h >> 13;
        h = h.wrapping_mul(0xc2b2ae35);
        h ^= h >> 16;
        h
    }

    pub fn constant_time_equal(a: u32, b: u32) -> bool {
        (a ^ b) == 0
    }
}
