#!/usr/bin/env python3
"""
Generate customers table for TechHub e-commerce dataset.

This script generates 50 diverse customer records using the Faker library
to ensure realistic names, addresses, and contact information with proper
geographic and demographic distributions.

Requirements:
    pip install faker
"""

import json
import random
from pathlib import Path

try:
    from faker import Faker
except ImportError:
    print("Error: Faker library not installed.")
    print("Please install it with: pip install faker")
    exit(1)

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data" / "structured"
NUM_CUSTOMERS = 50

# Regional distributions (from plan lines 672-692)
REGIONAL_BATCHES = [
    {
        "name": "West Coast",
        "states": ["CA", "OR", "WA"],
        "segments": {"Consumer": 9, "Corporate": 1},
    },
    {
        "name": "East Coast",
        "states": ["NY", "MA", "PA", "FL", "GA"],
        "segments": {"Consumer": 8, "Corporate": 2},
    },
    {
        "name": "Midwest",
        "states": ["IL", "MI", "OH", "MN"],
        "segments": {"Consumer": 9, "Home Office": 1},
    },
    {
        "name": "South",
        "states": ["TX", "NC", "TN", "LA"],
        "segments": {"Consumer": 8, "Corporate": 2},
    },
    {
        "name": "Mixed",
        "states": ["AZ", "NV", "CO", "UT", "OR", "WA", "CA"],
        "segments": {"Consumer": 6, "Corporate": 3, "Home Office": 1},
    },
]


def generate_customer_batch(batch_config, start_id, fake):
    """Generate a batch of customers for a specific region."""
    customers = []
    customer_num = start_id

    for segment, count in batch_config["segments"].items():
        for _ in range(count):
            # Generate realistic name
            name = fake.name()

            # Generate email based on segment
            if segment == "Corporate":
                # Corporate emails use company domains
                company_domains = [
                    "techstartup.com",
                    "lawfirm.com",
                    "consulting.com",
                    "healthcare.com",
                    "finance.com",
                    "agency.com",
                    "realestate.com",
                    "startup.com",
                    "nonprofit.org",
                ]
                domain = random.choice(company_domains)
                # Use role-based emails for corporate
                roles = [
                    "purchasing",
                    "it.dept",
                    "procurement",
                    "office.manager",
                    "tech.lead",
                    "it.admin",
                    "it.purchasing",
                ]
                email = f"{random.choice(roles)}@{domain}"
            elif segment == "Home Office":
                # Home office with professional feel
                first = name.split()[0].lower()
                domains = ["gmail.com", "freelance.com", "consultant.com"]
                prefixes = ["freelance.designer", "consultant.tech"]
                if random.random() < 0.5:
                    email = f"{random.choice(prefixes)}@gmail.com"
                else:
                    email = (
                        f"{first}.{fake.last_name().lower()}@{random.choice(domains)}"
                    )
            else:
                # Consumer - use common email providers
                first = name.split()[0].lower()
                last = name.split()[-1].lower()
                domains = ["gmail.com", "yahoo.com", "icloud.com"]
                email = f"{first}.{last}@{random.choice(domains)}"

            # Select state from batch region
            state = random.choice(batch_config["states"])

            # Generate city for that state (Faker has state-specific cities)
            city = fake.city()

            # Generate phone in US format
            phone = fake.numerify("###-###-####")

            customer = {
                "customer_id": f"CUST-{str(customer_num).zfill(3)}",
                "email": email,
                "name": name,
                "phone": phone,
                "city": city,
                "state": state,
                "segment": segment,
            }

            customers.append(customer)
            customer_num += 1

    return customers, customer_num


def generate_customers():
    """Generate all 50 customers with regional and demographic diversity."""
    # Initialize Faker with US locale
    fake = Faker("en_US")

    # Set seed for reproducibility
    Faker.seed(42)
    random.seed(42)

    print("=" * 60)
    print("TechHub Customers Data Generator")
    print("=" * 60)
    print(f"Target customers: {NUM_CUSTOMERS}")
    print()

    all_customers = []
    current_id = 1

    # Generate each regional batch
    for batch in REGIONAL_BATCHES:
        print(f"Generating {batch['name']} customers...")
        customers, current_id = generate_customer_batch(batch, current_id, fake)
        all_customers.extend(customers)

        # Show batch summary
        segment_counts = {}
        for customer in customers:
            segment = customer["segment"]
            segment_counts[segment] = segment_counts.get(segment, 0) + 1

        print(f"  ✓ Generated {len(customers)} customers:")
        for segment, count in segment_counts.items():
            print(f"    - {segment}: {count}")

    print(f"\n✓ Total customers generated: {len(all_customers)}")

    return all_customers


def validate_customers(customers):
    """Validate generated customers."""
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    # Check count
    print(f"\n✓ Total customers: {len(customers)} (expected: {NUM_CUSTOMERS})")
    assert len(customers) == NUM_CUSTOMERS

    # Check unique emails
    emails = [c["email"] for c in customers]
    assert len(emails) == len(set(emails)), "Duplicate emails found!"
    print(f"✓ All emails unique")

    # Check unique customer IDs
    ids = [c["customer_id"] for c in customers]
    assert len(ids) == len(set(ids)), "Duplicate customer IDs found!"
    print(f"✓ All customer IDs unique")

    # Check segment distribution
    segment_counts = {}
    for customer in customers:
        segment = customer["segment"]
        segment_counts[segment] = segment_counts.get(segment, 0) + 1

    print(f"\nSegment Distribution:")
    for segment in ["Consumer", "Corporate", "Home Office"]:
        count = segment_counts.get(segment, 0)
        percentage = (count / len(customers)) * 100
        print(f"  {segment}: {count} ({percentage:.1f}%)")

    # Validate expected distribution
    assert segment_counts["Consumer"] == 40, "Consumer count mismatch"
    assert segment_counts["Corporate"] == 8, "Corporate count mismatch"
    assert segment_counts["Home Office"] == 2, "Home Office count mismatch"
    print(f"✓ Segment distribution matches target")

    # Check all required fields present
    required_fields = [
        "customer_id",
        "email",
        "name",
        "phone",
        "city",
        "state",
        "segment",
    ]
    for customer in customers:
        for field in required_fields:
            assert field in customer, f"Missing field: {field}"
            assert customer[field], f"Empty field: {field}"
    print(f"✓ All required fields present and non-empty")

    print("\n" + "=" * 60)
    print("✓ ALL VALIDATIONS PASSED")
    print("=" * 60)


def main():
    """Main execution function."""
    # Generate customers
    customers = generate_customers()

    # Validate
    validate_customers(customers)

    # Save to file
    output_path = DATA_DIR / "customers.json"
    with open(output_path, "w") as f:
        json.dump(customers, f, indent=2)

    print(f"\n✓ Customers saved to: {output_path}")
    print("\nNext steps:")
    print("  1. Run python generate_orders.py")
    print("  2. Run python generate_order_items.py")
    print("  3. Run python create_database.py")
    print("  4. Run python validate_database.py")


if __name__ == "__main__":
    main()
