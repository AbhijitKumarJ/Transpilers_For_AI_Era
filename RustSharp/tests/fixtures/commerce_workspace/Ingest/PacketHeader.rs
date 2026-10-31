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

