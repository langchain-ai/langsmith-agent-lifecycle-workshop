-- Sample Queries for TechHub Workshop Scenarios
-- These queries demonstrate the multi-agent system use cases

-- ============================================================
-- Scenario 1: Customer Verification (HITL)
-- ============================================================
-- User: "Show me my orders"
-- Flow: Supervisor asks for email → verify customer → query orders

-- Step 1: Verify customer by email
SELECT customer_id, name, email
FROM customers 
WHERE email = 'sarah.chen@gmail.com';

-- Expected: Returns 1 customer record


-- ============================================================
-- Scenario 2: Order Status Check
-- ============================================================
-- User: "What's the status of my orders?"

-- Get all orders for a customer (most recent first)
SELECT order_id, order_date, status, tracking_number, total_amount
FROM orders 
WHERE customer_id = 'CUST-001'
ORDER BY order_date DESC;

-- Expected: Returns all orders for Sarah Chen, sorted by date


-- ============================================================
-- Scenario 3: What Did Customer Buy? (DB + RAG Coordination)
-- ============================================================
-- User: "I ordered a MacBook last week, what are the ports on it?"
-- Flow: DB Agent finds laptop → RAG Agent gets specs

-- Find customer's laptop purchases
SELECT o.order_date, p.name, p.product_id, p.category, oi.quantity, oi.price_per_unit
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.customer_id = 'CUST-001'
AND p.category = 'Laptops'
ORDER BY o.order_date DESC;

-- Expected: Returns laptop purchases with product IDs for RAG lookup


-- ============================================================
-- Scenario 4: Refund Calculation
-- ============================================================
-- User: "I want to return my laptop, how much will I get back?"

-- Get most recent laptop order for refund calculation
SELECT o.order_id, o.total_amount, o.order_date, o.status, p.name, p.category
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.customer_id = 'CUST-001' 
AND p.category = 'Laptops'
ORDER BY o.order_date DESC
LIMIT 1;

-- Expected: Returns order details for refund policy application


-- ============================================================
-- Scenario 5: Product Availability
-- ============================================================
-- User: "What laptops do you have in stock?"

-- Get available laptops
SELECT product_id, name, price, in_stock
FROM products 
WHERE category = 'Laptops' 
AND in_stock = 1
ORDER BY price;

-- Expected: Returns in-stock laptops sorted by price


-- ============================================================
-- Scenario 6: Bundle Analysis (What People Buy Together)
-- ============================================================
-- User: "What accessories do people usually buy with this laptop?"

-- Find products commonly purchased together
SELECT 
    p1.name as main_product, 
    p2.name as bought_with, 
    COUNT(*) as times_together
FROM order_items oi1
JOIN order_items oi2 ON oi1.order_id = oi2.order_id 
    AND oi1.product_id < oi2.product_id  -- Avoid duplicates
JOIN products p1 ON oi1.product_id = p1.product_id
JOIN products p2 ON oi2.product_id = p2.product_id
WHERE p1.product_id = 'TECH-LAP-001'  -- MacBook Air M2
GROUP BY p1.name, p2.name
ORDER BY times_together DESC
LIMIT 10;

-- Expected: Returns top 10 products bought with MacBook Air M2


-- ============================================================
-- Scenario 7: Order Tracking
-- ============================================================
-- User: "Where is my order ORD-2024-0001?"

-- Get order details with tracking
SELECT order_id, order_date, status, shipped_date, tracking_number, total_amount
FROM orders
WHERE order_id = 'ORD-2024-0001';

-- Expected: Returns order status and tracking info


-- ============================================================
-- Scenario 8: Recent Orders Needing Attention
-- ============================================================
-- Workshop scenario: Show orders still processing

-- Get processing orders (older than 3 days needs attention)
SELECT order_id, customer_id, order_date, status, 
       julianday('now') - julianday(order_date) as days_since_order
FROM orders
WHERE status = 'Processing'
AND julianday('now') - julianday(order_date) > 3
ORDER BY order_date;

-- Expected: Returns stuck orders needing investigation


-- ============================================================
-- Additional Useful Queries
-- ============================================================

-- Top customers by order count
SELECT c.customer_id, c.name, c.segment, COUNT(o.order_id) as order_count,
       SUM(o.total_amount) as total_spent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status != 'Cancelled'
GROUP BY c.customer_id, c.name, c.segment
ORDER BY order_count DESC
LIMIT 10;


-- Revenue by product category
SELECT p.category, 
       COUNT(DISTINCT oi.order_id) as orders,
       SUM(oi.quantity) as units_sold,
       SUM(oi.quantity * oi.price_per_unit) as revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status != 'Cancelled'
GROUP BY p.category
ORDER BY revenue DESC;


-- Products never ordered
SELECT product_id, name, category, price, in_stock
FROM products
WHERE product_id NOT IN (SELECT DISTINCT product_id FROM order_items)
ORDER BY category, name;


-- Average order value by customer segment
SELECT c.segment,
       COUNT(DISTINCT o.order_id) as order_count,
       AVG(o.total_amount) as avg_order_value,
       SUM(o.total_amount) as total_revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.status != 'Cancelled'
GROUP BY c.segment
ORDER BY avg_order_value DESC;


-- Orders with multiple items (good for testing product affinity)
SELECT o.order_id, o.customer_id, COUNT(oi.order_item_id) as item_count,
       o.total_amount,
       GROUP_CONCAT(p.name, ' | ') as products
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
GROUP BY o.order_id, o.customer_id, o.total_amount
HAVING item_count > 1
ORDER BY item_count DESC
LIMIT 20;


-- Shipping performance (orders delivered within expected timeframe)
SELECT 
    status,
    AVG(julianday(shipped_date) - julianday(order_date)) as avg_days_to_ship
FROM orders
WHERE shipped_date IS NOT NULL
GROUP BY status;

