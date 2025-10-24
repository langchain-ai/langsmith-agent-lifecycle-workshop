# TechHub Dataset Generation

This directory contains all the scripts and documentation for generating the synthetic e-commerce dataset used in the LangGraph multi-agent workshop.

## Overview

The TechHub dataset is a high-quality synthetic dataset designed to teach enterprise customers how to build multi-agent systems using LangChain's LangGraph. It simulates a customer support system for a consumer electronics e-commerce store.

**Dataset Contents:**
- 25 products (laptops, monitors, keyboards, audio, accessories)
- 50 customers (diverse profiles across Consumer, Corporate, Home Office segments)
- 250 orders (spanning 2 years with realistic patterns)
- ~440 order items (with product affinity patterns)
- SQLite database (156 KB, optimized for queries)

## Quick Start - Full Regeneration

To regenerate the complete dataset from scratch:

```bash
# Step 0: Manually create/edit products.json in ../data/structured/
# (Products are statically defined - see products.json for template)

# Step 1: Generate customers (requires: pip install faker)
python generate_customers.py

# Step 2: Generate orders
python generate_orders.py

# Step 3: Generate order items and calculate totals
python generate_order_items.py

# Step 4: Create SQLite database
python create_database.py

# Step 5: Validate everything
python validate_database.py
```

**Total time:** ~5 minutes (plus manual product definition)

## Generation Process

### Step 0: Products (Static Definition)

**File:** `../data/structured/products.json`

Products are manually defined in JSON format with exact specifications from the project plan. This gives us complete control over the product catalog for workshop scenarios.

**Why static?**
- Only 25 products - easy to manually define
- Exact names/prices needed for workshop demos
- No need for generation script complexity

**To modify:** Simply edit `../data/structured/products.json` directly.

### Step 1: Generate Customers

**Script:** `generate_customers.py`  
**Output:** `../data/structured/customers.json`  
**Requirements:** `pip install faker`

Generates 50 diverse customer records using the Faker library for realistic names, addresses, and contact information.

**Features:**
- Regional distribution (West Coast, East Coast, Midwest, South)
- Demographic diversity (various names, valid city/state pairs)
- Segment distribution: 80% Consumer, 16% Corporate, 4% Home Office
- Reproducible with seed=42

**Customization:**
- Modify `NUM_CUSTOMERS` for different counts
- Adjust `REGIONAL_BATCHES` for different geographic distributions
- Change `Faker.seed()` for different random customers

### Step 2: Generate Orders

**Script:** `generate_orders.py`  
**Output:** `../data/structured/orders.json`  
**Dependencies:** customers.json, products.json

Generates 250 orders with realistic temporal and behavioral patterns.

**Features:**
- Date range: Oct 2023 - Oct 2025 (configurable via `CURRENT_DATE`)
- Seasonal patterns (Q4 has 40% more orders than Q2)
- Power law customer distribution (20% of customers = 60% of orders)
- Status distribution: 80% Delivered, 12% Shipped, 7% Processing, 1% Cancelled
- Realistic tracking numbers and shipping dates

**Customization:**
- Change `CURRENT_DATE` to adjust date anchor
- Modify `NUM_ORDERS` for different order counts
- Adjust `random.seed(42)` for different patterns

### Step 3: Generate Order Items

**Script:** `generate_order_items.py`  
**Output:** `../data/structured/order_items.json` + updates `../data/structured/orders.json` totals  
**Dependencies:** customers.json, products.json, orders.json

Generates ~440 order items with product affinity patterns and calculates order totals.

**Features:**
- Product affinity (laptops bought with accessories, monitors with keyboards)
- Realistic quantity patterns (86% qty=1, 12% qty=2, 3% qty=3+)
- Price variations (±5% for historical pricing)
- Automatic order total calculation

**Customization:**
- Modify product affinity logic in `select_products_for_order()`
- Adjust quantity distributions in `determine_items_per_order()`
- Change pricing variance in `calculate_price_per_unit()`

### Step 4: Create Database

**Script:** `create_database.py`  
**Output:** `../data/structured/techhub.db`  
**Dependencies:** All JSON files

Creates SQLite database with full schema, constraints, and indexes. See `../data/structured/SCHEMA.md` for complete schema documentation.

**Features:**
- 4 tables (customers, products, orders, order_items)
- Foreign key constraints
- CHECK constraints for data integrity
- 7 indexes for query performance
- Foreign key enforcement enabled

**Schema:** See lines 1284-1336 in `project_plan/full_project_plan.md`

### Step 5: Validate Database

**Script:** `validate_database.py`  
**Input:** `../data/structured/techhub.db`  
**Output:** Comprehensive validation report

Runs extensive validation checks on the generated database.

**Validations:**
- Record counts (50 customers, 25 products, 250 orders, ~440 items)
- Foreign key integrity (no orphaned records)
- Date logic (shipped_date >= order_date)
- Status distributions (within expected ranges)
- Order totals match line items
- Price variations within ±5%
- Query performance (<100ms target)

## File Descriptions

### Generation Scripts

| File | Purpose | Time |
|------|---------|------|
| `generate_customers.py` | Generate 50 customer records with Faker | ~5 sec |
| `generate_orders.py` | Generate 250 orders with patterns | ~10 sec |
| `generate_order_items.py` | Generate ~440 items + totals | ~15 sec |
| `create_database.py` | Create SQLite database | ~5 sec |
| `validate_database.py` | Comprehensive validation | ~2 sec |

### Supporting Files

| File | Purpose |
|------|---------|
| `sample_queries.sql` | Workshop scenario SQL queries |
| `project_plan/` | Complete project planning documents |

## Dependencies

**Required:**
- Python 3.8+ (tested on 3.13)
- Standard library only for most scripts

**Optional:**
- `faker` library (for generate_customers.py): `pip install faker`

## Data Characteristics

### Products (25)
- **Laptops (5):** $899 - $1,999
- **Monitors (4):** $199 - $599
- **Keyboards & Mice (6):** $39 - $149
- **Audio (5):** $79 - $399
- **Accessories (5):** $19 - $79
- **In stock:** 22 (3 out of stock for realism)

### Customers (50)
- **Consumer:** 40 (80%) - gmail, yahoo, icloud emails
- **Corporate:** 8 (16%) - company domain emails  
- **Home Office:** 2 (4%) - professional/freelance emails
- **Geographic:** Distributed across US regions
- **Diversity:** Various names, valid city/state pairs

### Orders (250)
- **Date range:** Oct 2023 - Oct 2025
- **Delivered:** 200 (80%)
- **Shipped:** 30 (12%)
- **Processing:** 17 (7%)
- **Cancelled:** 3 (1%)
- **Customer distribution:** Power law (heavy/medium/light buyers)

### Order Items (~440)
- **Average items per order:** 1.8
- **Quantity distribution:** 86% qty=1, 12% qty=2, 3% qty=3+
- **Product affinity:** Laptops with accessories, monitors with keyboards
- **Price variance:** 80% at current price, 20% with ±5% variation

### Database (156 KB)
- **Query performance:** All queries <1ms
- **Indexes:** 7 indexes on key fields
- **Constraints:** Full foreign key and CHECK constraint enforcement
- **Integrity:** Zero validation errors

## Reproducibility

All scripts use fixed random seeds (`random.seed(42)`, `Faker.seed(42)`) for reproducibility. Running the same scripts with the same inputs will produce identical outputs.

**To get different data:**
- Comment out or change seed values in each script
- Modify configuration constants (NUM_CUSTOMERS, NUM_ORDERS, etc.)
- Adjust date ranges or distribution parameters

## Troubleshooting

### "Faker library not installed"
```bash
pip install faker
```

### "Database file not found"
Make sure you've run `create_database.py` before `validate_database.py`

### "Foreign key violations"
Regenerate in order: customers → orders → order_items → database

### "Total amount mismatches"
This should not happen - indicates a bug in `generate_order_items.py`. Please regenerate.

## Workshop Integration

This dataset supports key LangGraph workshop scenarios:

1. **HITL (Human-in-the-Loop):** Customer verification before showing orders
2. **Multi-agent coordination:** Database agent + RAG agent working together
3. **Persistence & Memory:** Maintaining conversation state across turns
4. **Evaluation:** Multiple eval types (final response, trajectory, single-step, multi-turn)

See `sample_queries.sql` for example workshop queries.

## Additional Resources

- **Schema documentation:** `../data/structured/SCHEMA.md` (complete database schema reference)
- **Documents overview:** `../data/documents/DOCUMENTS_OVERVIEW.md` (complete RAG corpus documentation)
- **Full project plan:** `project_plan/full_project_plan.md` (comprehensive 2000+ line spec)
- **Sample queries:** `sample_queries.sql` (workshop scenario queries)
- **Main README:** `../README.md` (usage instructions for workshop participants)

## Questions or Issues?

This is synthetic data for educational purposes. For questions about:
- **Dataset design:** See `project_plan/full_project_plan.md`
- **Generation process:** See this README or script comments
- **Workshop scenarios:** See `sample_queries.sql`
- **Data quality:** Run `validate_database.py`

---

**Generated:** October 2025  
**Purpose:** LangGraph Multi-Agent Workshop  
**License:** Synthetic data, free to use and distribute

