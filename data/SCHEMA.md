# TechHub Database Schema

**Database:** `techhub.db` (SQLite 3)  
**Purpose:** E-commerce customer support system for workshop scenarios  
**Records:** 50 customers, 25 products, 250 orders, 439 order items

## Overview

This database contains synthetic data for a consumer electronics e-commerce store called "TechHub." The schema supports customer support scenarios including order tracking, product queries, refund processing, and multi-agent coordination between database and RAG agents.

**Key Characteristics:**
- Full referential integrity with foreign key constraints
- CHECK constraints for data validation
- 7 indexes for query optimization
- Date range: October 2023 - October 2025
- All queries execute in <1ms

## Tables

### 1. customers

Stores customer account information for all buyers.

**Record Count:** 50

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `customer_id` | TEXT | PRIMARY KEY | Unique customer identifier. Format: `CUST-001` to `CUST-050` |
| `email` | TEXT | UNIQUE, NOT NULL | Customer's email address (used for verification) |
| `name` | TEXT | NOT NULL | Customer's full name |
| `phone` | TEXT | | Customer's phone number. Format: `###-###-####` |
| `city` | TEXT | NOT NULL | Customer's city |
| `state` | TEXT | NOT NULL | Customer's state (2-letter US state code) |
| `segment` | TEXT | NOT NULL, CHECK | Customer segment. Valid values: `'Consumer'`, `'Corporate'`, `'Home Office'` |

**Indexes:**
- `idx_customers_email` on `email` (for fast customer lookup)

**Relationships:**
- Referenced by `orders.customer_id` (one customer has many orders)

**Data Distribution:**
- Consumer: 40 customers (80%)
- Corporate: 8 customers (16%)
- Home Office: 2 customers (4%)
- Geographic: Distributed across US regions (CA, NY, TX, IL, FL, etc.)

**Sample Records:**
```sql
customer_id: CUST-001
email: sarah.chen@gmail.com
name: Sarah Chen
segment: Consumer
city: San Francisco
state: CA
```

**Business Rules:**
- Email addresses are unique and used for customer verification (HITL scenarios)
- Corporate customers have company domain emails (@company.com)
- Consumer customers have personal emails (@gmail.com, @yahoo.com, @icloud.com)

---

### 2. products

Product catalog containing all items available for purchase.

**Record Count:** 25

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `product_id` | TEXT | PRIMARY KEY | Unique product identifier. Format: `TECH-XXX-###` where XXX is category code |
| `name` | TEXT | NOT NULL | Product name and key specifications |
| `category` | TEXT | NOT NULL, CHECK | Product category. Valid values: `'Laptops'`, `'Monitors'`, `'Keyboards'`, `'Audio'`, `'Accessories'` |
| `price` | REAL | NOT NULL, CHECK > 0 | Current product price in USD |
| `in_stock` | INTEGER | NOT NULL, CHECK IN (0, 1) | Stock status. `1` = in stock, `0` = out of stock |

**Indexes:**
- `idx_products_category` on `category` (for category-based queries)

**Relationships:**
- Referenced by `order_items.product_id` (products appear in order line items)

**Category Distribution:**
- Laptops: 5 products (IDs: TECH-LAP-001 to TECH-LAP-005)
- Monitors: 4 products (IDs: TECH-MON-006 to TECH-MON-009)
- Keyboards: 6 products (IDs: TECH-KEY-010 to TECH-KEY-015, includes mice)
- Audio: 5 products (IDs: TECH-AUD-016 to TECH-AUD-020)
- Accessories: 5 products (IDs: TECH-ACC-021 to TECH-ACC-025)

**Price Ranges:**
- Laptops: $899 - $1,999
- Monitors: $199 - $599
- Keyboards/Mice: $39 - $149
- Audio: $79 - $399
- Accessories: $19 - $79

**Stock Status:**
- In stock: 22 products (88%)
- Out of stock: 3 products (12%)

**Sample Records:**
```sql
product_id: TECH-LAP-001
name: MacBook Air M2 (13-inch, 256GB)
category: Laptops
price: 1199.00
in_stock: 1
```

**Business Rules:**
- Products can appear in orders even if currently out of stock (historical orders)
- Product IDs encode category information in the prefix

---

### 3. orders

Order records tracking customer purchases over time.

**Record Count:** 250

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `order_id` | TEXT | PRIMARY KEY | Unique order identifier. Format: `ORD-YYYY-####` (year + sequence) |
| `customer_id` | TEXT | NOT NULL, FOREIGN KEY | References `customers.customer_id` |
| `order_date` | DATE | NOT NULL | Date order was placed. Format: `YYYY-MM-DD` |
| `status` | TEXT | NOT NULL, CHECK | Order status. Valid values: `'Processing'`, `'Shipped'`, `'Delivered'`, `'Cancelled'` |
| `shipped_date` | DATE | | Date order was shipped. Format: `YYYY-MM-DD`. NULL if not yet shipped |
| `tracking_number` | TEXT | | Shipping tracking number. Format: `1Z999AA1XXXXXXXX`. NULL if not shipped |
| `total_amount` | REAL | NOT NULL, CHECK >= 0 | Order total in USD (sum of all line items) |

**Indexes:**
- `idx_orders_customer` on `customer_id` (for customer order history)
- `idx_orders_date` on `order_date` (for date range queries)
- `idx_orders_status` on `status` (for status filtering)

**Relationships:**
- References `customers.customer_id` (many orders belong to one customer)
- Referenced by `order_items.order_id` (one order has many line items)

**Status Distribution:**
- Delivered: 200 orders (80%)
- Shipped: 30 orders (12%)
- Processing: 17 orders (7%)
- Cancelled: 3 orders (1%)

**Date Range:**
- Earliest order: October 2023
- Latest order: October 2025
- Seasonal pattern: Q4 (Nov-Dec) has ~40% more orders than Q2 (Apr-Jun)

**Sample Records:**
```sql
order_id: ORD-2024-0123
customer_id: CUST-001
order_date: 2024-08-15
status: Delivered
shipped_date: 2024-08-17
tracking_number: 1Z999AA145678901
total_amount: 1248.00
```

**Business Rules:**
1. `shipped_date` must be >= `order_date` when not NULL
2. `shipped_date` is NULL for `status` = 'Processing' or 'Cancelled'
3. `tracking_number` is NULL for `status` = 'Processing' or 'Cancelled'
4. `total_amount` is 0 for `status` = 'Cancelled'
5. Order IDs are sequential within each year
6. Delivered orders have `shipped_date` at least 7 days before current date
7. Shipped orders have `shipped_date` within last 7 days

**Customer Behavior:**
- Power law distribution: 20% of customers generate 60% of orders
- Heavy buyers (10 customers): 6-10 orders each
- Medium buyers (15 customers): 4-6 orders each
- Light buyers (25 customers): 1-5 orders each

---

### 4. order_items

Line items for each order, representing individual products purchased.

**Record Count:** 439

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `order_item_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Auto-generated unique line item identifier |
| `order_id` | TEXT | NOT NULL, FOREIGN KEY | References `orders.order_id` |
| `product_id` | TEXT | NOT NULL, FOREIGN KEY | References `products.product_id` |
| `quantity` | INTEGER | NOT NULL, CHECK > 0 | Quantity ordered (typically 1-5) |
| `price_per_unit` | REAL | NOT NULL, CHECK > 0 | Price per unit in USD at time of order |

**Indexes:**
- `idx_order_items_order` on `order_id` (for order details queries)
- `idx_order_items_product` on `product_id` (for product sales analysis)

**Relationships:**
- References `orders.order_id` (many items belong to one order)
- References `products.product_id` (many items refer to one product)

**Quantity Distribution:**
- Quantity 1: ~380 items (86%)
- Quantity 2: ~45 items (10%)
- Quantity 3+: ~14 items (3%)

**Items Per Order:**
- 1 item: ~134 orders (54%)
- 2 items: ~66 orders (27%)
- 3 items: ~29 orders (12%)
- 4-5 items: ~19 orders (8%)

**Price Variation:**
- 80% of items priced at current product price
- 20% of items priced within ±5% (simulates historical price changes)

**Sample Records:**
```sql
order_item_id: 245
order_id: ORD-2024-0123
product_id: TECH-LAP-001
quantity: 1
price_per_unit: 1199.00
```

**Business Rules:**
1. Cancelled orders (status = 'Cancelled') have NO order_items
2. Sum of (`quantity` × `price_per_unit`) for all items in an order equals `orders.total_amount`
3. `price_per_unit` is within ±5% of current `products.price`
4. Product affinity patterns:
   - Laptops often purchased with accessories (hub, sleeve, mouse)
   - Monitors often purchased with keyboards/mice
   - Audio products typically purchased alone
   - Corporate customers buy keyboards/mice in larger quantities

---

## Relationships Diagram

```
customers (50)
    ↓ 1:N
orders (250)
    ↓ 1:N
order_items (439)
    ↓ N:1
products (25)
```

**Foreign Keys:**
- `orders.customer_id` → `customers.customer_id`
- `order_items.order_id` → `orders.order_id`
- `order_items.product_id` → `products.product_id`

All foreign keys are enforced with `PRAGMA foreign_keys = ON`.

---

## Common Query Patterns

### Customer Verification (HITL)
```sql
-- Find customer by email
SELECT customer_id, name, email, segment
FROM customers 
WHERE email = 'sarah.chen@gmail.com';
```

### Order History
```sql
-- Get customer's orders (most recent first)
SELECT order_id, order_date, status, tracking_number, total_amount
FROM orders 
WHERE customer_id = 'CUST-001'
ORDER BY order_date DESC;
```

### Order Details
```sql
-- Get full order details with line items
SELECT 
    o.order_id,
    o.order_date,
    o.status,
    p.name as product_name,
    oi.quantity,
    oi.price_per_unit,
    (oi.quantity * oi.price_per_unit) as line_total
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.order_id = 'ORD-2024-0123';
```

### Product Availability
```sql
-- Find available products in a category
SELECT product_id, name, price
FROM products 
WHERE category = 'Laptops' 
AND in_stock = 1
ORDER BY price;
```

### Customer Purchase History
```sql
-- What products has a customer bought?
SELECT DISTINCT
    p.name,
    p.category,
    p.price as current_price,
    o.order_date
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.customer_id = 'CUST-001'
AND o.status != 'Cancelled'
ORDER BY o.order_date DESC;
```

### Product Bundle Analysis
```sql
-- Find products commonly bought together
SELECT 
    p1.name as product1,
    p2.name as product2,
    COUNT(*) as times_purchased_together
FROM order_items oi1
JOIN order_items oi2 ON oi1.order_id = oi2.order_id 
    AND oi1.product_id < oi2.product_id
JOIN products p1 ON oi1.product_id = p1.product_id
JOIN products p2 ON oi2.product_id = p2.product_id
GROUP BY p1.name, p2.name
ORDER BY times_purchased_together DESC
LIMIT 10;
```

### Order Status Summary
```sql
-- Count orders by status
SELECT 
    status,
    COUNT(*) as order_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 1) as percentage
FROM orders
GROUP BY status
ORDER BY order_count DESC;
```

### Revenue Analysis
```sql
-- Revenue by product category
SELECT 
    p.category,
    COUNT(DISTINCT oi.order_id) as num_orders,
    SUM(oi.quantity) as units_sold,
    SUM(oi.quantity * oi.price_per_unit) as total_revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status != 'Cancelled'
GROUP BY p.category
ORDER BY total_revenue DESC;
```

### Recent Processing Orders
```sql
-- Orders still processing (may need attention)
SELECT 
    order_id,
    customer_id,
    order_date,
    julianday('now') - julianday(order_date) as days_since_order
FROM orders
WHERE status = 'Processing'
ORDER BY order_date;
```

---

## Business Logic & Constraints

### Valid Values

**Customer Segments:**
- `'Consumer'` - Individual buyers (80%)
- `'Corporate'` - Business buyers (16%)
- `'Home Office'` - Small business/freelancers (4%)

**Product Categories:**
- `'Laptops'` - Laptop computers
- `'Monitors'` - Computer displays
- `'Keyboards'` - Keyboards and mice
- `'Audio'` - Headphones, speakers, microphones
- `'Accessories'` - Hubs, stands, webcams, sleeves, cables

**Order Statuses:**
- `'Processing'` - Order received, not yet shipped
- `'Shipped'` - Order shipped, in transit
- `'Delivered'` - Order delivered to customer
- `'Cancelled'` - Order cancelled (no items, zero total)

### Invariants

1. **No orphaned records**: All foreign keys must reference existing records
2. **Date consistency**: `shipped_date` >= `order_date` when not NULL
3. **Status consistency**: 
   - Processing/Cancelled orders have NULL `shipped_date` and `tracking_number`
   - Delivered orders have non-NULL `shipped_date` and `tracking_number`
4. **Financial accuracy**: `orders.total_amount` = SUM(`order_items.quantity` × `order_items.price_per_unit`)
5. **Cancelled order rules**: 
   - Must have `total_amount` = 0
   - Must have no records in `order_items`
6. **Price bounds**: `order_items.price_per_unit` within ±5% of `products.price`
7. **Quantity limits**: `order_items.quantity` in range 1-5

### Data Quality

- Zero foreign key violations
- Zero date logic errors
- 100% order total accuracy (within $0.02 rounding tolerance)
- All queries execute in <1ms
- All CHECK constraints enforced
- Full referential integrity maintained

---

## Tips for Text-to-SQL Agents

1. **Always verify customer identity first**: Use email to look up `customer_id` before querying orders
2. **Join tables properly**: Use explicit JOINs rather than implicit joins for clarity
3. **Filter cancelled orders**: Usually exclude `status = 'Cancelled'` from analysis queries
4. **Use indexes**: Queries on `customer_id`, `order_date`, `status`, `email`, `category` are fast
5. **Check NULL values**: `shipped_date` and `tracking_number` are NULL for processing/cancelled orders
6. **Format assumptions**: 
   - Dates are YYYY-MM-DD
   - Customer IDs are CUST-###
   - Order IDs are ORD-YYYY-####
   - Product IDs are TECH-XXX-###
7. **Aggregations**: Use GROUP BY when counting/summing by category, segment, or status
8. **Date functions**: Use SQLite date functions like `julianday()` for date arithmetic
9. **Case sensitivity**: Text comparisons are case-sensitive by default
10. **Decimal precision**: Use ROUND() for financial calculations to avoid floating point issues

---

## Metadata

**Database File:** `techhub.db`  
**Size:** 156 KB  
**SQLite Version:** 3.x  
**Created:** October 2025  
**Purpose:** LangGraph Multi-Agent Workshop Dataset  
**Status:** Production-ready, fully validated

For data regeneration instructions, see `../data_generation/README.md`

