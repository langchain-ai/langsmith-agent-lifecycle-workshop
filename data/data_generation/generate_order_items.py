#!/usr/bin/env python3
"""
Generate order_items table for TechHub e-commerce dataset.

This script generates ~500 order items with realistic patterns:
- Product affinity (laptops bought with accessories, monitors with keyboards)
- Quantity patterns based on customer segment
- Price variations (±5% for historical pricing)
- Calculates and updates order totals
"""

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data" / "structured"
TARGET_ITEMS = 500


def load_data():
    """Load all required data files."""
    with open(DATA_DIR / "customers.json", "r") as f:
        customers = json.load(f)

    with open(DATA_DIR / "products.json", "r") as f:
        products = json.load(f)

    with open(DATA_DIR / "orders.json", "r") as f:
        orders = json.load(f)

    return customers, products, orders


def determine_items_per_order(customer_segment):
    """
    Determine how many items in this order based on customer segment.

    Distribution:
    - Consumer: 60% have 1 item, 25% have 2, 10% have 3, 5% have 4-5
    - Corporate: Skewed toward more items
    """
    if customer_segment == "Corporate":
        weights = [0.30, 0.30, 0.25, 0.15]  # More multi-item orders
    else:
        weights = [0.60, 0.25, 0.10, 0.05]  # Mostly single items

    num_items_options = [1, 2, 3, random.randint(4, 5)]
    num_items = random.choices(num_items_options, weights=weights)[0]
    return num_items


def select_products_for_order(num_items, products, customer_segment):
    """
    Select products with realistic affinity patterns.

    Rules:
    - Laptop orders often include accessories (hub, sleeve, mouse)
    - Monitor orders often include keyboards/mice
    - Audio products typically ordered alone or with other audio
    - Accessories rarely ordered solo (usually with main product)
    - Corporate customers prefer keyboards/mice in quantity
    """
    # Group products by category
    products_by_category = defaultdict(list)
    for product in products:
        # Only include in-stock products for new orders (some historical orders may have out-of-stock items)
        products_by_category[product["category"]].append(product)

    selected = []

    # First item: Pick anchor product (weighted by category)
    if customer_segment == "Corporate":
        # Corporate prefers laptops and monitors
        category_weights = {
            "Laptops": 0.35,
            "Monitors": 0.30,
            "Keyboards": 0.20,
            "Audio": 0.10,
            "Accessories": 0.05,
        }
    else:
        # Consumer more balanced
        category_weights = {
            "Laptops": 0.25,
            "Monitors": 0.15,
            "Keyboards": 0.20,
            "Audio": 0.25,
            "Accessories": 0.15,
        }

    # Select anchor product
    available_categories = [
        cat for cat in category_weights.keys() if products_by_category[cat]
    ]
    if not available_categories:
        return []

    anchor_category = random.choices(
        available_categories,
        weights=[category_weights[cat] for cat in available_categories],
    )[0]

    anchor_products = products_by_category[anchor_category]
    if not anchor_products:
        return []

    anchor = random.choice(anchor_products)
    selected.append(anchor)

    # Select additional items based on affinity
    if num_items > 1:
        if anchor["category"] == "Laptops":
            # Add accessories: hub, sleeve, mouse, stand
            accessory_pool = products_by_category["Accessories"] + [
                p for p in products_by_category["Keyboards"] if "Mouse" in p["name"]
            ]
            # Remove duplicates
            accessory_pool = [p for p in accessory_pool if p not in selected]

            if accessory_pool:
                num_accessories = min(num_items - 1, len(accessory_pool))
                selected.extend(random.sample(accessory_pool, num_accessories))

        elif anchor["category"] == "Monitors":
            # Add keyboards/mice
            keyboard_pool = [
                p for p in products_by_category["Keyboards"] if p not in selected
            ]

            if keyboard_pool:
                num_keyboards = min(num_items - 1, len(keyboard_pool))
                selected.extend(random.sample(keyboard_pool, num_keyboards))

        elif anchor["category"] == "Audio":
            # Often solo, but might add other audio or accessories
            if num_items > 1 and random.random() < 0.3:  # 30% chance to add more
                audio_pool = [p for p in products_by_category["Audio"] if p != anchor]
                if audio_pool:
                    selected.append(random.choice(audio_pool))

        elif anchor["category"] == "Keyboards":
            # Add mouse or other keyboard items
            keyboard_pool = [
                p for p in products_by_category["Keyboards"] if p != anchor
            ]

            if keyboard_pool:
                num_more = min(num_items - 1, len(keyboard_pool))
                selected.extend(random.sample(keyboard_pool, num_more))

        elif anchor["category"] == "Accessories":
            # Accessories often come with main products, but can be bundled together
            # Add laptop or monitor as main product
            if random.random() < 0.7:  # 70% chance to have main product
                main_categories = ["Laptops", "Monitors"]
                main_products = []
                for cat in main_categories:
                    main_products.extend(products_by_category[cat])

                if main_products:
                    selected.append(random.choice(main_products))

            # Fill remaining with more accessories
            if len(selected) < num_items:
                accessory_pool = [
                    p for p in products_by_category["Accessories"] if p not in selected
                ]
                num_more = min(num_items - len(selected), len(accessory_pool))
                if accessory_pool:
                    selected.extend(random.sample(accessory_pool, num_more))

    # Fill remaining slots with random products if needed
    while len(selected) < num_items:
        remaining = [p for p in products if p not in selected]
        if remaining:
            selected.append(random.choice(remaining))
        else:
            break

    return selected[:num_items]


def determine_quantity(product, customer_segment):
    """
    Determine quantity for this product.

    Most items quantity=1, occasional 2-3 for accessories/keyboards.
    Corporate buyers more likely to buy multiples.
    """
    if customer_segment == "Corporate":
        # Corporate might buy multiple keyboards/mice for office
        if product["category"] in ["Keyboards", "Accessories"]:
            return random.choices([1, 2, 3], weights=[0.50, 0.35, 0.15])[0]
        else:
            return random.choices([1, 2], weights=[0.85, 0.15])[0]
    else:
        # Consumer mostly quantity=1
        if product["category"] == "Accessories":
            return random.choices([1, 2], weights=[0.85, 0.15])[0]
        else:
            return 1  # Almost always 1 for laptops, monitors, audio


def calculate_price_per_unit(product_current_price, order_date):
    """
    Simulate price changes over time.

    - 80% at current price
    - 20% with ±5% variation (sales, price changes)
    """
    if random.random() < 0.80:
        return product_current_price
    else:
        # ±5% variation
        variation = random.uniform(-0.05, 0.05)
        adjusted_price = product_current_price * (1 + variation)
        return round(adjusted_price, 2)


def generate_order_items(orders, customers, products):
    """Generate all order items with realistic patterns."""
    order_items = []
    item_id_counter = 1

    # Create lookup dictionaries
    customer_lookup = {c["customer_id"]: c for c in customers}
    product_lookup = {p["product_id"]: p for p in products}

    print(f"Generating order items for {len(orders)} orders...")

    for i, order in enumerate(orders):
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(orders)} orders...")

        # Skip cancelled orders (no items)
        if order["status"] == "Cancelled":
            continue

        # Get customer segment
        customer = customer_lookup[order["customer_id"]]
        segment = customer["segment"]

        # Determine number of items
        num_items = determine_items_per_order(segment)

        # Select products
        selected_products = select_products_for_order(num_items, products, segment)

        if not selected_products:
            # Fallback: select random product
            selected_products = [random.choice(products)]

        # Create order items
        order_total = 0.0
        for product in selected_products:
            quantity = determine_quantity(product, segment)
            price_per_unit = calculate_price_per_unit(
                product["price"], order["order_date"]
            )

            line_total = quantity * price_per_unit
            order_total += line_total

            order_item = {
                "order_item_id": item_id_counter,
                "order_id": order["order_id"],
                "product_id": product["product_id"],
                "quantity": quantity,
                "price_per_unit": price_per_unit,
            }
            order_items.append(order_item)
            item_id_counter += 1

        # Update order total_amount
        order["total_amount"] = round(order_total, 2)

    return order_items


def validate_order_items(order_items, orders, products, customers):
    """Validate generated order items against requirements."""
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    # Check record count
    print(f"\n✓ Total order items: {len(order_items)}")
    assert (
        420 <= len(order_items) <= 600
    ), f"Expected 420-600 order items, got {len(order_items)}"
    print(f"  (Target range: 420-600, ~500 typical)")

    # Create lookup dictionaries
    order_lookup = {o["order_id"]: o for o in orders}
    product_lookup = {p["product_id"]: p for p in products}

    # Check all order_ids exist
    invalid_orders = [
        item for item in order_items if item["order_id"] not in order_lookup
    ]
    assert (
        len(invalid_orders) == 0
    ), f"Found {len(invalid_orders)} items with invalid order_ids"
    print(f"✓ All order_ids valid")

    # Check all product_ids exist
    invalid_products = [
        item for item in order_items if item["product_id"] not in product_lookup
    ]
    assert (
        len(invalid_products) == 0
    ), f"Found {len(invalid_products)} items with invalid product_ids"
    print(f"✓ All product_ids valid")

    # Check quantity values
    invalid_quantities = [
        item for item in order_items if not (1 <= item["quantity"] <= 5)
    ]
    assert (
        len(invalid_quantities) == 0
    ), f"Found {len(invalid_quantities)} items with quantity outside 1-5 range"
    print(f"✓ All quantities in valid range (1-5)")

    # Check price variations
    price_errors = []
    for item in order_items:
        product = product_lookup[item["product_id"]]
        price_diff_pct = (
            abs(item["price_per_unit"] - product["price"]) / product["price"] * 100
        )
        if price_diff_pct > 5.5:  # Allow small rounding tolerance
            price_errors.append(
                {
                    "product": product["name"],
                    "current_price": product["price"],
                    "item_price": item["price_per_unit"],
                    "diff_pct": price_diff_pct,
                }
            )

    assert (
        len(price_errors) == 0
    ), f"Found {len(price_errors)} items with >5% price variance"
    print(f"✓ All prices within ±5% of current product price")

    # Check no cancelled orders have items
    cancelled_orders = {o["order_id"] for o in orders if o["status"] == "Cancelled"}
    cancelled_with_items = [
        item for item in order_items if item["order_id"] in cancelled_orders
    ]
    assert (
        len(cancelled_with_items) == 0
    ), f"Found {len(cancelled_with_items)} items for cancelled orders"
    print(f"✓ No cancelled orders have items")

    # Check order totals match line items
    order_totals = defaultdict(float)
    for item in order_items:
        order_totals[item["order_id"]] += item["quantity"] * item["price_per_unit"]

    total_mismatches = []
    for order in orders:
        if order["status"] == "Cancelled":
            continue

        calculated_total = round(order_totals[order["order_id"]], 2)
        stored_total = order["total_amount"]

        if (
            abs(calculated_total - stored_total) > 0.02
        ):  # Allow 2 cent tolerance for rounding
            total_mismatches.append(
                {
                    "order_id": order["order_id"],
                    "calculated": calculated_total,
                    "stored": stored_total,
                    "diff": calculated_total - stored_total,
                }
            )

    assert (
        len(total_mismatches) == 0
    ), f"Found {len(total_mismatches)} orders with total mismatches"
    print(f"✓ All order totals match sum of line items")

    # Check product distribution
    product_counts = Counter(item["product_id"] for item in order_items)
    category_counts = Counter()
    for product_id, count in product_counts.items():
        product = product_lookup[product_id]
        category_counts[product["category"]] += count

    print(f"\nProduct Distribution by Category:")
    for category in sorted(category_counts.keys()):
        count = category_counts[category]
        percentage = (count / len(order_items)) * 100
        print(f"  {category}: {count} items ({percentage:.1f}%)")

    # Check quantity distribution
    quantity_counts = Counter(item["quantity"] for item in order_items)
    print(f"\nQuantity Distribution:")
    for qty in sorted(quantity_counts.keys()):
        count = quantity_counts[qty]
        percentage = (count / len(order_items)) * 100
        print(f"  Quantity {qty}: {count} items ({percentage:.1f}%)")

    # Check items per order distribution
    items_per_order = Counter()
    for order in orders:
        if order["status"] != "Cancelled":
            num_items = sum(
                1 for item in order_items if item["order_id"] == order["order_id"]
            )
            items_per_order[num_items] += 1

    print(f"\nItems Per Order Distribution:")
    for num_items in sorted(items_per_order.keys()):
        count = items_per_order[num_items]
        total_orders = len([o for o in orders if o["status"] != "Cancelled"])
        percentage = (count / total_orders) * 100
        print(f"  {num_items} items: {count} orders ({percentage:.1f}%)")

    print("\n" + "=" * 60)
    print("✓ ALL VALIDATIONS PASSED")
    print("=" * 60)


def main():
    """Main execution function."""
    print("=" * 60)
    print("TechHub Order Items Data Generator")
    print("=" * 60)
    print(f"Target items: ~{TARGET_ITEMS}")
    print()

    # Set random seed for reproducibility (optional - comment out for different results each run)
    random.seed(42)

    # Load data
    print("Loading customers, products, and orders...")
    customers, products, orders = load_data()
    print(f"✓ Loaded {len(customers)} customers")
    print(f"✓ Loaded {len(products)} products")
    print(f"✓ Loaded {len(orders)} orders")
    print()

    # Generate order items
    order_items = generate_order_items(orders, customers, products)
    print(f"✓ Generated {len(order_items)} order items")

    # Validate
    validate_order_items(order_items, orders, products, customers)

    # Save order items
    output_path = DATA_DIR / "order_items.json"
    with open(output_path, "w") as f:
        json.dump(order_items, f, indent=2)

    print(f"\n✓ Order items saved to: {output_path}")

    # Update orders with calculated totals
    orders_path = DATA_DIR / "orders.json"
    with open(orders_path, "w") as f:
        json.dump(orders, f, indent=2)

    print(f"✓ Updated order totals in: {orders_path}")

    print("\n" + "=" * 60)
    print("DATA GENERATION COMPLETE!")
    print("=" * 60)
    print("\nGenerated files:")
    print(f"  - {DATA_DIR / 'products.json'} (25 products)")
    print(f"  - {DATA_DIR / 'customers.json'} (50 customers)")
    print(f"  - {DATA_DIR / 'orders.json'} ({len(orders)} orders)")
    print(f"  - {DATA_DIR / 'order_items.json'} ({len(order_items)} items)")
    print("\nNext steps:")
    print("  - Review the generated data")
    print("  - Create the SQLite database")
    print("  - Generate RAG documentation")


if __name__ == "__main__":
    main()
