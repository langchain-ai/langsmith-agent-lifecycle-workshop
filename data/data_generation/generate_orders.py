#!/usr/bin/env python3
"""
Generate orders table for TechHub e-commerce dataset.

This script generates 250 orders with realistic patterns:
- Date distribution spanning 2 years with seasonal patterns
- Customer assignment following power law distribution
- Status calculation based on dates (Delivered, Shipped, Processing, Cancelled)
- Realistic tracking numbers
"""

import datetime
import json
import random
from collections import Counter
from pathlib import Path

# Configuration
CURRENT_DATE = datetime.date(2025, 10, 20)  # Configurable anchor date
NUM_ORDERS = 250
DATA_DIR = Path(__file__).parent.parent / "data" / "structured"


def load_customers():
    """Load customers from JSON file."""
    with open(DATA_DIR / "customers.json", "r") as f:
        return json.load(f)


def load_products():
    """Load products from JSON file (for validation)."""
    with open(DATA_DIR / "products.json", "r") as f:
        return json.load(f)


def generate_order_dates(num_orders=NUM_ORDERS, current_date=CURRENT_DATE):
    """
    Generate order dates spanning past 2 years with seasonal patterns.

    Q4 (Nov-Dec) gets 40% more orders than Q2 (Apr-Jun).
    Weekend orders are 20% lower than weekdays.
    """
    start_date = current_date - datetime.timedelta(days=730)  # 2 years ago

    # Generate more dates than needed to apply seasonal filters
    candidate_dates = []
    attempts = 0
    max_attempts = num_orders * 10

    while len(candidate_dates) < num_orders and attempts < max_attempts:
        attempts += 1
        days_ago = random.randint(0, 730)
        order_date = current_date - datetime.timedelta(days=days_ago)

        # Apply seasonal pattern
        month = order_date.month
        keep_probability = 0.5  # Base probability

        if month in [11, 12]:  # Q4 boost
            keep_probability = 0.7
        elif month in [4, 5, 6]:  # Q2 slower
            keep_probability = 0.35

        # Apply weekend pattern (reduce by 20%)
        if order_date.weekday() >= 5:  # Saturday=5, Sunday=6
            keep_probability *= 0.8

        if random.random() < keep_probability:
            candidate_dates.append(order_date)

    # Sort by date for cleaner order IDs
    return sorted(candidate_dates[:num_orders])


def assign_customers_to_orders(customer_ids, num_orders=NUM_ORDERS):
    """
    Assign customers to orders following power law distribution.

    20% of customers generate 60% of orders:
    - Heavy buyers (10 customers): 6-10 orders each (~80 orders)
    - Medium buyers (15 customers): 4-6 orders each (~75 orders)
    - Light buyers (25 customers): 1-5 orders each (~95 orders)
    """
    assignments = []

    # Shuffle customers to randomize who becomes heavy/medium/light buyer
    shuffled_customers = customer_ids.copy()
    random.shuffle(shuffled_customers)

    # Heavy buyers (10 customers → ~80 orders)
    heavy_buyers = shuffled_customers[:10]
    for cust in heavy_buyers:
        orders_for_customer = random.randint(6, 10)
        assignments.extend([cust] * orders_for_customer)

    # Medium buyers (15 customers → ~75 orders)
    medium_buyers = shuffled_customers[10:25]
    for cust in medium_buyers:
        orders_for_customer = random.randint(4, 6)
        assignments.extend([cust] * orders_for_customer)

    # Light buyers (25 customers → remaining orders)
    light_buyers = shuffled_customers[25:]
    remaining_orders = num_orders - len(assignments)

    # Distribute remaining orders among light buyers
    for i in range(remaining_orders):
        cust = light_buyers[i % len(light_buyers)]
        assignments.append(cust)

    # Shuffle to mix up the order assignment
    random.shuffle(assignments)

    return assignments[:num_orders]


def calculate_order_status(order_date, current_date=CURRENT_DATE):
    """
    Calculate realistic order status based on dates.

    Target distribution:
    - 80% Delivered (shipped >7 days ago)
    - 12% Shipped (shipped 1-7 days ago)
    - 7% Processing (not yet shipped)
    - 1% Cancelled (rare)
    """
    # Calculate days since order
    days_since_order = (current_date - order_date).days

    # 1.5% chance of cancellation (to ensure we get ~3 cancelled orders)
    if random.random() < 0.015:
        return {"status": "Cancelled", "shipped_date": None, "tracking_number": None}

    # Orders from last 10 days might still be processing
    # Use probability curve: more recent = higher chance of still processing
    if days_since_order <= 10:
        # Days 0-2: 80% chance of processing
        # Days 3-5: 50% chance of processing
        # Days 6-10: 20% chance of processing
        if days_since_order <= 2:
            processing_chance = 0.80
        elif days_since_order <= 5:
            processing_chance = 0.50
        else:
            processing_chance = 0.20

        if random.random() < processing_chance:
            return {
                "status": "Processing",
                "shipped_date": None,
                "tracking_number": None,
            }

    # Generate shipped_date (1-3 days after order)
    ship_delay = random.randint(1, 3)
    shipped_date = order_date + datetime.timedelta(days=ship_delay)

    # Generate tracking number
    tracking = f"1Z999AA1{random.randint(10000000, 99999999)}"

    # Determine if shipped or delivered based on current date
    days_since_ship = (current_date - shipped_date).days

    if days_since_ship > 7:
        status = "Delivered"
    elif days_since_ship >= 0:
        status = "Shipped"
    else:
        # Ship date is in future (shouldn't happen with logic above)
        status = "Processing"
        shipped_date = None
        tracking = None

    return {
        "status": status,
        "shipped_date": shipped_date.isoformat() if shipped_date else None,
        "tracking_number": tracking,
    }


def generate_order_id(order_date, sequence_num):
    """Generate order ID in format: ORD-YYYY-####"""
    year = order_date.year
    order_num = str(sequence_num).zfill(4)
    return f"ORD-{year}-{order_num}"


def adjust_status_distribution(orders, current_date):
    """
    Adjust order statuses to match target distribution.

    This ensures workshop scenarios have enough examples of each status type,
    even though naturally most old orders would be delivered.
    """
    target_delivered = int(0.80 * len(orders))  # 200
    target_shipped = int(0.12 * len(orders))  # 30
    target_processing = int(0.07 * len(orders))  # 17
    target_cancelled = (
        len(orders) - target_delivered - target_shipped - target_processing
    )  # 3

    # Count current distribution
    current_counts = Counter(o["status"] for o in orders)

    # If we have too many delivered (which is likely), convert some to other statuses
    if current_counts["Delivered"] > target_delivered:
        # Get delivered orders sorted by date (most recent first)
        delivered_orders = [o for o in orders if o["status"] == "Delivered"]
        delivered_orders.sort(key=lambda x: x["order_date"], reverse=True)

        # Convert some recent delivered orders to shipped
        num_shipped_needed = target_shipped - current_counts.get("Shipped", 0)
        for i in range(min(num_shipped_needed, len(delivered_orders))):
            order = delivered_orders[i]
            # Set shipped date to recent (1-7 days ago)
            shipped_date = current_date - datetime.timedelta(days=random.randint(1, 7))
            order["status"] = "Shipped"
            order["shipped_date"] = shipped_date.isoformat()
            if not order["tracking_number"]:
                order["tracking_number"] = (
                    f"1Z999AA1{random.randint(10000000, 99999999)}"
                )

        # Convert some to processing
        num_processing_needed = target_processing - current_counts.get("Processing", 0)
        start_idx = num_shipped_needed
        for i in range(start_idx, start_idx + num_processing_needed):
            if i < len(delivered_orders):
                order = delivered_orders[i]
                # Adjust order date to be recent (0-5 days ago) for processing orders
                recent_date = current_date - datetime.timedelta(
                    days=random.randint(0, 5)
                )
                order["order_date"] = recent_date.isoformat()
                order["status"] = "Processing"
                order["shipped_date"] = None
                order["tracking_number"] = None

        # Convert some to cancelled
        num_cancelled_needed = target_cancelled - current_counts.get("Cancelled", 0)
        start_idx = num_shipped_needed + num_processing_needed
        for i in range(start_idx, start_idx + num_cancelled_needed):
            if i < len(delivered_orders):
                order = delivered_orders[i]
                order["status"] = "Cancelled"
                order["shipped_date"] = None
                order["tracking_number"] = None

    return orders


def generate_orders(customers, current_date=CURRENT_DATE):
    """Generate all orders with realistic patterns."""
    # Generate dates
    print(f"Generating {NUM_ORDERS} order dates...")
    order_dates = generate_order_dates(NUM_ORDERS, current_date)

    # Assign customers
    print("Assigning customers to orders...")
    customer_ids = [c["customer_id"] for c in customers]
    customer_assignments = assign_customers_to_orders(customer_ids, NUM_ORDERS)

    # Group orders by year for sequential numbering
    orders_by_year = {}
    for order_date, customer_id in zip(order_dates, customer_assignments):
        year = order_date.year
        if year not in orders_by_year:
            orders_by_year[year] = []
        orders_by_year[year].append((order_date, customer_id))

    # Generate orders with sequential IDs per year
    print("Calculating order statuses...")
    orders = []
    for year in sorted(orders_by_year.keys()):
        year_orders = orders_by_year[year]
        for seq_num, (order_date, customer_id) in enumerate(year_orders, start=1):
            status_info = calculate_order_status(order_date, current_date)

            order = {
                "order_id": generate_order_id(order_date, seq_num),
                "customer_id": customer_id,
                "order_date": order_date.isoformat(),
                "status": status_info["status"],
                "shipped_date": status_info["shipped_date"],
                "tracking_number": status_info["tracking_number"],
                "total_amount": 0.00,  # Will be calculated by generate_order_items.py
            }
            orders.append(order)

    # Sort by order_id for consistency
    orders.sort(key=lambda x: x["order_id"])

    # Adjust distribution to match targets (80% Delivered, 12% Shipped, 7% Processing, 1% Cancelled)
    # This ensures workshop scenarios have enough examples of each status
    print("Adjusting status distribution to match targets...")
    orders = adjust_status_distribution(orders, current_date)

    return orders


def validate_orders(orders, customers):
    """Validate generated orders against requirements."""
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    # Check record count
    print(f"\n✓ Total orders: {len(orders)} (expected: {NUM_ORDERS})")
    assert len(orders) == NUM_ORDERS, f"Expected {NUM_ORDERS} orders, got {len(orders)}"

    # Check status distribution
    status_counts = Counter(o["status"] for o in orders)
    print(f"\nStatus Distribution:")
    for status in ["Delivered", "Shipped", "Processing", "Cancelled"]:
        count = status_counts[status]
        percentage = (count / len(orders)) * 100
        print(f"  {status}: {count} ({percentage:.1f}%)")

    # Validate expected ranges
    delivered_pct = (status_counts["Delivered"] / len(orders)) * 100
    shipped_pct = (status_counts["Shipped"] / len(orders)) * 100
    processing_pct = (status_counts["Processing"] / len(orders)) * 100
    cancelled_pct = (status_counts["Cancelled"] / len(orders)) * 100

    assert (
        70 <= delivered_pct <= 90
    ), f"Delivered should be ~80%, got {delivered_pct:.1f}%"
    assert 5 <= shipped_pct <= 20, f"Shipped should be ~12%, got {shipped_pct:.1f}%"
    assert (
        0 <= processing_pct <= 15
    ), f"Processing should be ~7%, got {processing_pct:.1f}%"
    assert 0 <= cancelled_pct <= 5, f"Cancelled should be ~1%, got {cancelled_pct:.1f}%"
    print("✓ Status distribution within expected ranges")

    # Check all customer_ids exist
    customer_ids = {c["customer_id"] for c in customers}
    invalid_customers = [o for o in orders if o["customer_id"] not in customer_ids]
    assert (
        len(invalid_customers) == 0
    ), f"Found {len(invalid_customers)} orders with invalid customer_ids"
    print(f"✓ All customer_ids valid")

    # Check date logic
    invalid_dates = []
    for order in orders:
        if order["shipped_date"]:
            order_date = datetime.date.fromisoformat(order["order_date"])
            shipped_date = datetime.date.fromisoformat(order["shipped_date"])
            if shipped_date < order_date:
                invalid_dates.append(order["order_id"])

    assert (
        len(invalid_dates) == 0
    ), f"Found {len(invalid_dates)} orders with shipped_date < order_date"
    print(f"✓ All date logic valid (shipped_date >= order_date)")

    # Check order_id format and uniqueness
    order_ids = [o["order_id"] for o in orders]
    assert len(order_ids) == len(set(order_ids)), "Duplicate order_ids found"

    for order_id in order_ids:
        assert order_id.startswith("ORD-"), f"Invalid order_id format: {order_id}"
        parts = order_id.split("-")
        assert len(parts) == 3, f"Invalid order_id format: {order_id}"
        assert (
            parts[1].isdigit() and len(parts[1]) == 4
        ), f"Invalid year in order_id: {order_id}"
        assert (
            parts[2].isdigit() and len(parts[2]) == 4
        ), f"Invalid sequence in order_id: {order_id}"

    print(f"✓ All order_ids valid and unique")

    # Check seasonal pattern
    order_months = [datetime.date.fromisoformat(o["order_date"]).month for o in orders]
    q4_orders = sum(1 for m in order_months if m in [11, 12])
    q2_orders = sum(1 for m in order_months if m in [4, 5, 6])

    print(f"\nSeasonal Pattern:")
    print(f"  Q4 (Nov-Dec): {q4_orders} orders")
    print(f"  Q2 (Apr-Jun): {q2_orders} orders")
    if q2_orders > 0:
        ratio = q4_orders / q2_orders
        print(f"  Ratio (Q4/Q2): {ratio:.2f}x (target: ~1.4x)")

    # Check customer distribution
    customer_order_counts = Counter(o["customer_id"] for o in orders)
    heavy_buyers = [c for c, count in customer_order_counts.items() if count >= 6]
    medium_buyers = [c for c, count in customer_order_counts.items() if 4 <= count < 6]
    light_buyers = [c for c, count in customer_order_counts.items() if count < 4]

    print(f"\nCustomer Distribution:")
    print(f"  Heavy buyers (6+ orders): {len(heavy_buyers)} customers")
    print(f"  Medium buyers (4-5 orders): {len(medium_buyers)} customers")
    print(f"  Light buyers (1-3 orders): {len(light_buyers)} customers")
    print(f"  Total unique customers: {len(customer_order_counts)}")

    print("\n" + "=" * 60)
    print("✓ ALL VALIDATIONS PASSED")
    print("=" * 60)


def main():
    """Main execution function."""
    print("=" * 60)
    print("TechHub Orders Data Generator")
    print("=" * 60)
    print(f"Current date anchor: {CURRENT_DATE}")
    print(f"Target orders: {NUM_ORDERS}")
    print()

    # Set random seed for reproducibility (optional - comment out for different results each run)
    random.seed(42)

    # Load dependencies
    print("Loading customers and products...")
    customers = load_customers()
    products = load_products()
    print(f"✓ Loaded {len(customers)} customers")
    print(f"✓ Loaded {len(products)} products")
    print()

    # Generate orders
    orders = generate_orders(customers, CURRENT_DATE)
    print(f"✓ Generated {len(orders)} orders")

    # Validate
    validate_orders(orders, customers)

    # Save to file
    output_path = DATA_DIR / "orders.json"
    with open(output_path, "w") as f:
        json.dump(orders, f, indent=2)

    print(f"\n✓ Orders saved to: {output_path}")
    print("\nNext step: Run generate_order_items.py to create order line items")


if __name__ == "__main__":
    main()
