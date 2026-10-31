use super::NativeCollider;

impl NativeCollider {
    pub fn check_aabb_overlap(
        min_x1: f64,
        max_x1: f64,
        min_y1: f64,
        max_y1: f64,
        min_x2: f64,
        max_x2: f64,
        min_y2: f64,
        max_y2: f64,
    ) -> bool {
        min_x1 <= max_x2 && max_x1 >= min_x2 && min_y1 <= max_y2 && max_y1 >= min_y2
    }

    pub fn distance(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
        let dx = x2 - x1;
        let dy = y2 - y1;
        (dx * dx + dy * dy).sqrt()
    }
}
