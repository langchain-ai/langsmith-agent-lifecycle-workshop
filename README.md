# TechHub E-Commerce Workshop Dataset

High-quality synthetic dataset for teaching LangGraph multi-agent systems in enterprise workshops.

## Overview

This dataset simulates a customer support system for "TechHub," a consumer electronics e-commerce store. It's designed to teach:
- Multi-agent systems with supervisor pattern
- Human-in-the-loop (HITL) for customer verification
- Database agent queries
- RAG agent for product specs and policies
- Offline evaluation (final response, trajectory, single-step, multi-turn)

## Directory Structure

```
lc-enablement-workshop/
├── data/                      # Dataset files (ready to use)
│   ├── structured/            # Tabular data and database
│   │   ├── SCHEMA.md          # Complete schema documentation
│   │   ├── products.json      # 25 products
│   │   ├── customers.json     # 50 customers
│   │   ├── orders.json        # 250 orders
│   │   ├── order_items.json   # 439 order items
│   │   └── techhub.db         # SQLite database
│   │
│   └── documents/             # RAG documents (unstructured)
│       ├── policies/          # 5 policy documents
│       ├── products/          # 25 product documents
│       └── DOCUMENTS_OVERVIEW.md  # RAG corpus documentation
│
├── data_generation/           # Generation scripts & documentation
│   ├── README.md              # Complete generation guide
│   ├── generate_customers.py
│   ├── generate_orders.py
│   ├── generate_order_items.py
│   ├── create_database.py
│   ├── validate_database.py
│   └── sample_queries.sql
│
└── README.md                  # This file
```

## Quick Start - Using the Dataset

The dataset is ready to use! All files are in the `data/` directory.

### With Python

```python
import sqlite3

# Connect to database
conn = sqlite3.connect('data/structured/techhub.db')
cursor = conn.cursor()

# Find customer by email (HITL scenario)
cursor.execute(
    "SELECT * FROM customers WHERE email = ?",
    ('sarah.chen@gmail.com',)
)
customer = cursor.fetchone()

# Get customer's orders
cursor.execute("""
    SELECT order_id, order_date, status, total_amount
    FROM orders 
    WHERE customer_id = ?
    ORDER BY order_date DESC
""", (customer[0],))

for order in cursor.fetchall():
    print(order)

conn.close()
```

### With SQLite CLI

```bash
# Open database
sqlite3 data/structured/techhub.db

# Try sample queries
.read data_generation/sample_queries.sql

# Or explore interactively
SELECT * FROM customers LIMIT 5;
SELECT COUNT(*) FROM orders WHERE status = 'Shipped';
```

### With JSON Files

```python
import json

# Load data
with open('data/structured/customers.json') as f:
    customers = json.load(f)

with open('data/structured/orders.json') as f:
    orders = json.load(f)

# Find customer
customer = next(c for c in customers if c['email'] == 'sarah.chen@gmail.com')

# Get their orders
customer_orders = [o for o in orders if o['customer_id'] == customer['customer_id']]
print(f"{customer['name']} has {len(customer_orders)} orders")
```

## Dataset Statistics

| Resource | Count | Details |
|----------|-------|---------|
| **Products** | 25 | 5 Laptops, 4 Monitors, 6 Keyboards, 5 Audio, 5 Accessories |
| **Customers** | 50 | 80% Consumer, 16% Corporate, 4% Home Office |
| **Orders** | 250 | 80% Delivered, 12% Shipped, 7% Processing, 1% Cancelled |
| **Order Items** | 439 | Avg 1.8 items/order with product affinity patterns |
| **Database** | 156 KB | Fully indexed, <1ms query performance |

### Product Categories

- **Laptops:** $899 - $1,999 (MacBook Air, MacBook Pro, Dell XPS, Lenovo ThinkPad, HP Pavilion)
- **Monitors:** $199 - $599 (Dell UltraSharp, LG, Samsung Curved, BenQ Designer)
- **Keyboards & Mice:** $39 - $149 (Apple Magic, Logitech MX, Gaming keyboards)
- **Audio:** $79 - $399 (Sony WH-1000XM5, AirPods Pro, Blue Yeti, JBL Flip)
- **Accessories:** $19 - $79 (USB-C Hub, Laptop Stand, Webcam, Laptop Sleeve, Cables)

## Workshop Scenarios

This dataset supports key LangGraph workshop scenarios:

### 1. Customer Verification (HITL)
```
User: "Show me my orders"
Flow: Supervisor → HITL (ask for email) → Database Agent → Response
```

### 2. Multi-Agent Coordination (DB + RAG)
```
User: "I ordered a MacBook last week, what ports does it have?"
Flow: Database Agent (find order) → RAG Agent (get specs) → Response
```

### 3. Complex Multi-Hop Query
```
User: "Can I return the monitor I bought and will it work with my Dell laptop?"
Flow: Database (find monitor) → RAG (return policy + compatibility) → Response
```

### 4. Order Tracking
```
User: "What's the status of order ORD-2024-0001?"
Flow: Database Agent → Response
```

### 5. Product Compatibility (Pure RAG)
```
User: "Do AirPods work with Windows laptops?"
Flow: RAG Agent (compatibility guide) → Response
```

### 6. Bundle Recommendations
```
User: "I'm buying a laptop, what else should I get?"
Flow: Database (bundle analysis) → RAG (product details) → Response
```

## Sample Queries

See `data_generation/sample_queries.sql` for complete workshop queries including:
- Customer verification
- Order status tracking
- Product bundle analysis
- Refund calculations
- Revenue by category
- Shipping performance metrics

## Data Regeneration

**Don't need to regenerate?** Skip this section - the data is ready to use!

To regenerate the dataset from scratch (e.g., for different data, learning purposes):

```bash
cd data_generation
python generate_customers.py   # Requires: pip install faker
python generate_orders.py
python generate_order_items.py
python create_database.py
python validate_database.py
```

**See `data_generation/README.md` for complete regeneration guide.**

## Data Characteristics

### Realistic Patterns

- **Temporal:** Orders span 2 years with seasonal patterns (Q4 spike)
- **Behavioral:** Power law distribution (20% of customers = 60% of orders)
- **Product Affinity:** Laptops bought with accessories, monitors with keyboards
- **Pricing:** 80% at current price, 20% with ±5% historical variance
- **Geographic:** Customers distributed across US regions

### Data Quality

- ✅ Zero foreign key violations
- ✅ Zero date logic errors
- ✅ 100% order total accuracy
- ✅ Perfect segment distributions
- ✅ All queries <1ms (target: <100ms)

## Documentation

### Database Schema

**For complete schema documentation** (including all constraints, relationships, query patterns, and tips for text-to-SQL agents), see **`data/structured/SCHEMA.md`**.

### RAG Document Corpus

**For complete document corpus documentation** (including document structure, policy details, content guidelines, and multi-agent scenario support), see **`data/documents/DOCUMENTS_OVERVIEW.md`**.

### Database Quick Overview

```sql
customers (50 records)
├── customer_id (PK)
├── email (UNIQUE)
├── name
├── phone
├── city
├── state
└── segment (Consumer/Corporate/Home Office)

products (25 records)
├── product_id (PK)
├── name
├── category (Laptops/Monitors/Keyboards/Audio/Accessories)
├── price
└── in_stock (0/1)

orders (250 records)
├── order_id (PK)
├── customer_id (FK → customers)
├── order_date
├── status (Processing/Shipped/Delivered/Cancelled)
├── shipped_date
├── tracking_number
└── total_amount

order_items (439 records)
├── order_item_id (PK, AUTOINCREMENT)
├── order_id (FK → orders)
├── product_id (FK → products)
├── quantity
└── price_per_unit
```

7 indexes on key fields for optimal query performance.

## Workshop Materials

### ✅ Completed
- Synthetic dataset (products, customers, orders, order_items)
- SQLite database with full schema and indexes
- Sample queries for workshop scenarios
- Comprehensive validation

### 🔜 Coming Next
1. **RAG Documents:** 30 markdown files (25 product docs + 5 policy docs)
2. **Multi-Agent System:** Supervisor, Database Agent, RAG Agent implementation
3. **Evaluation Sets:** Test cases for various evaluation types
4. **Notebooks:** Workshop jupyter notebooks with exercises

## Use Cases

This dataset is designed for:

- **Teaching LangGraph:** Multi-agent systems, HITL, persistence, memory
- **Evaluation Practice:** All eval types (final response, trajectory, single-step, multi-turn)
- **Agent Development:** Database agent, RAG agent, supervisor patterns
- **Production Deployment:** Monitoring, data flywheels, annotation queues

## License

Synthetic data created for educational purposes. Free to use and distribute.

## Additional Resources

- **Database Schema:** `data/structured/SCHEMA.md` - Complete database documentation
- **RAG Documents:** `data/documents/DOCUMENTS_OVERVIEW.md` - Complete corpus documentation
- **Generation Guide:** `data_generation/README.md` - How to regenerate dataset
- **Project Plan:** `data_generation/project_plan/full_project_plan.md` - Full specification
- **Sample Queries:** `data_generation/sample_queries.sql` - Workshop SQL queries
- **Validation:** Run `python data_generation/validate_database.py` anytime

---

**Questions?** See `data_generation/README.md` for detailed documentation on dataset design, generation process, and customization options.
