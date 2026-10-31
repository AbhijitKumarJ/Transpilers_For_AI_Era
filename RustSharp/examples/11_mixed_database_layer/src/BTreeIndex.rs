use std::collections::BTreeMap;
use std::sync::RwLock;

static INDEX: RwLock<Option<BTreeMap<String, u64>>> = RwLock::new(None);

use super::BTreeIndex;

impl BTreeIndex {
    pub fn insert_entry(key: &str, offset: u64) {
        let mut guard = INDEX.write().unwrap();
        if guard.is_none() {
            *guard = Some(BTreeMap::new());
        }
        if let Some(map) = guard.as_mut() {
            map.insert(key.to_string(), offset);
        }
    }

    pub fn contains_key(key: &str) -> bool {
        let guard = INDEX.read().unwrap();
        if let Some(map) = guard.as_ref() {
            map.contains_key(key)
        } else {
            false
        }
    }
}
