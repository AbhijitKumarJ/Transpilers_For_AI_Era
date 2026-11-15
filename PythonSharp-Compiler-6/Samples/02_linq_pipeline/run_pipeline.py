"""Sample 02: Demonstrates passing Python data structures to PythonSharp compiled records and executing fused LINQ queries from Python."""

import sys
from pathlib import Path

# Add compiled dist/ to path
out_dir = Path(__file__).parent / "dist"
sys.path.insert(0, str(out_dir))

from data_pipeline.models import Product  # noqa: E402
from data_pipeline.services import InventoryAnalytics  # noqa: E402

if __name__ == "__main__":
    print("--- Initializing Inventory from Python ---")
    raw_products = [
        Product(id=1, name="Mechanical Keyboard", category="Electronics", price=120.0, stock=45),
        Product(id=2, name="Wireless Mouse", category="Electronics", price=45.0, stock=110),
        Product(id=3, name="USB-C Hub", category="Electronics", price=35.0, stock=85),
        Product(id=4, name="Standing Desk", category="Furniture", price=450.0, stock=12),
        Product(id=5, name="Ergonomic Chair", category="Furniture", price=290.0, stock=20),
        Product(id=6, name="4K Monitor", category="Electronics", price=399.0, stock=25),
    ]

    analytics = InventoryAnalytics(raw_products)

    print("\n--- Top 2 Stocked Electronics (LINQ query) ---")
    top_electronics = analytics.get_top_stocked_names("Electronics", 2)
    for item in top_electronics:
        print(f"  • {item}")

    print("\n--- Category Total Value (LINQ .Sum()) ---")
    electronics_value = analytics.calculate_total_value("Electronics")
    print(f"Total value of Electronics: ${electronics_value:,.2f}")

    furniture_value = analytics.calculate_total_value("Furniture")
    print(f"Total value of Furniture: ${furniture_value:,.2f}")
