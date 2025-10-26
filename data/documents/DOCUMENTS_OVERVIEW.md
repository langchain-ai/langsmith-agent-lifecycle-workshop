# TechHub RAG Document Corpus Overview

**Location:** `data/documents/`  
**Purpose:** Unstructured content for RAG (Retrieval-Augmented Generation) agent queries  
**Total Documents:** 30 (25 product documents + 5 policy documents)  
**Format:** Markdown (.md)

## Overview

This document corpus provides comprehensive product information and store policies for the TechHub e-commerce customer support system. The documents complement the structured database by providing detailed technical specifications, setup instructions, troubleshooting guides, and policy details that would be impractical to store in a relational database.

**Key Characteristics:**
- All documents use consistent structure and formatting
- Product names and IDs match database records exactly
- Policy references are internally consistent across all documents
- Real technical specifications from manufacturer sources
- Designed for natural language RAG retrieval

---

## Directory Structure

```
data/documents/
├── products/           # 25 product-specific documents
│   ├── TECH-LAP-001.md through TECH-LAP-005.md  (5 laptops)
│   ├── TECH-MON-006.md through TECH-MON-009.md  (4 monitors)
│   ├── TECH-KEY-010.md through TECH-KEY-015.md  (6 keyboards/mice)
│   ├── TECH-AUD-016.md through TECH-AUD-020.md  (5 audio products)
│   └── TECH-ACC-021.md through TECH-ACC-025.md  (5 accessories)
│
└── policies/          # 5 store-wide policy documents
    ├── return_policy.md
    ├── warranty_guide.md
    ├── shipping_guide.md
    ├── compatibility_guide.md
    └── support_faq.md
```

---

## Product Documents (25 Files)

### File Naming Convention
**Format:** `{product_id}.md` where product IDs follow pattern `TECH-{CATEGORY}-{NUMBER}`

### Standard Document Structure

Each product document follows this 7-section structure:

1. **Product Overview** - What it is, target audience, key value proposition (2-3 sentences)
2. **Key Specifications** - Technical specs in bullet format (10-15 items, varies by category)
3. **Compatibility** - OS compatibility, connection requirements, works with which products, adapter needs
4. **What's Included** - Box contents, cables, accessories
5. **Setup & Getting Started** - 5-step setup process from unboxing to first use
6. **Common Questions** - 5 standardized Q&As covering upgradability, compatibility, warranty, returns, software/accessories
7. **Troubleshooting** - 3 common issues with specific, actionable solutions

**Word Count:** 400-700 words per document depending on product complexity

### Product Catalog by Category

#### Laptops (5 documents) - TECH-LAP-001 to TECH-LAP-005
1. MacBook Air M2 (13-inch, 256GB) - $1,199
2. MacBook Pro M3 (14-inch, 512GB) - $1,999
3. Dell XPS 13 (Intel i7, 512GB) - $1,399
4. Lenovo ThinkPad X1 Carbon (Intel i7, 1TB) - $1,699
5. HP Pavilion 15 (AMD Ryzen 5, 256GB) - $899

#### Monitors (4 documents) - TECH-MON-006 to TECH-MON-009
6. Dell UltraSharp 27" 4K Monitor - $549
7. LG 24" 1080p Monitor - $199
8. Samsung 32" Curved Gaming Monitor - $449
9. BenQ 27" Designer Monitor (Color Accurate) - $599

#### Keyboards & Mice (6 documents) - TECH-KEY-010 to TECH-KEY-015
10. Apple Magic Keyboard - $99
11. Logitech MX Keys Wireless Keyboard - $119
12. Mechanical Gaming Keyboard (RGB, Cherry MX) - $149
13. Apple Magic Mouse - $79
14. Logitech MX Master 3S Mouse - $99
15. Wireless Mouse & Keyboard Combo - $39

#### Audio (5 documents) - TECH-AUD-016 to TECH-AUD-020
16. Sony WH-1000XM5 Wireless Headphones - $399
17. AirPods Pro (2nd Generation) - $249
18. Blue Yeti USB Microphone - $129
19. Logitech USB Desktop Speakers - $79
20. JBL Flip 6 Bluetooth Speaker - $129

#### Accessories (5 documents) - TECH-ACC-021 to TECH-ACC-025
21. USB-C Hub (7-in-1, HDMI, USB-A, SD) - $49
22. Aluminum Laptop Stand (Adjustable) - $45
23. Logitech C920 Webcam (1080p) - $79
24. Laptop Sleeve (13-15 inch, Water Resistant) - $29
25. Cable Management Kit (10 pieces) - $19

---

## Policy Documents (5 Files)

### 1. return_policy.md (~350 words)

**Purpose:** Define return eligibility, windows, and process

**Key Policies:**
- Unopened electronics: 30-day return window
- Opened electronics: 14-day return window
- 15% restocking fee for opened items over $500 (no fee for defects or items under $500)
- 5-step return process with RMA numbers
- Refunds to original payment method in 5-7 business days

**Critical for:** HITL return authorization scenarios, refund calculations

---

### 2. warranty_guide.md (~320 words)

**Purpose:** Explain warranty coverage and claim process

**Key Policies:**
- All products include manufacturer's 1-year limited warranty
- Covers manufacturing defects and hardware failures
- Excludes accidental damage, water damage, normal wear and tear
- Extended warranty options available (AppleCare+, manufacturer plans)
- Claims processed through manufacturers, TechHub facilitates

**Critical for:** Defect vs damage determination, warranty claim routing

---

### 3. shipping_guide.md (~310 words)

**Purpose:** Explain shipping options, timing, and delivery

**Key Policies:**
- Standard (5-7 days): FREE on $50+, $7.99 under $50
- Express (2-3 days): $14.99 flat rate
- Orders before 2 PM ET ship same day
- Carriers: UPS, FedEx, USPS
- Signature required for orders over $500

**Critical for:** Order status queries, delivery timeframe questions

---

### 4. compatibility_guide.md (~680 words) ⭐ **CRITICAL FOR MULTI-AGENT**

**Purpose:** Cross-product compatibility reference for building complete setups

**Key Content:**
- Mac to PC product compatibility (what works seamlessly, what needs adapters)
- Monitor connection guide by laptop model (MacBook, Dell, Lenovo, HP)
- USB-C and Thunderbolt explained (ports, protocols, backward compatibility)
- Common product combinations (Home Office, Student, Content Creator, Gaming setups)
- Adapter requirements summary by platform
- Power delivery and charging specs

**Why Critical:** Enables queries like "Will this monitor work with my MacBook?" that require DB agent (identify customer's laptop) + RAG agent (compatibility rules). Contains cross-product relationships not in database.

**Critical for:** Setup recommendations, troubleshooting connectivity, product bundling

---

### 5. support_faq.md (~340 words)

**Purpose:** General customer support questions not product-specific

**Key Content:**
- Order tracking methods
- Modifying/canceling orders
- Account management
- Contact methods (phone, email, live chat with hours)
- Payment options and price matching
- Security and privacy policies

**Critical for:** Contact routing, account questions, payment issues

---

## Content Quality Standards

### Consistency Requirements

**Product Names & IDs:**
- Product names match database `products.name` exactly
- Product IDs use format `TECH-XXX-###` matching database `products.product_id`
- Filenames use product IDs exactly

**Policy References (Standardized Across All Documents):**
- 14-day return window for opened electronics
- 30-day return window for unopened items
- 15% restocking fee for opened items over $500
- 1-year manufacturer warranty
- Free shipping on orders $50+
- Contact: 1-800-555-TECH, support@techhub.com

**Price Consistency:**
- Product prices in documents must match database `products.price`
- Combo pricing calculated from current prices

### Writing Standards

- Professional but accessible tone
- Real specifications from manufacturer sources (no hallucinated specs)
- Specific troubleshooting solutions (not generic "contact support")
- Consistent markdown formatting (H1 for title, H2 for sections, bullets for lists)

---

## Workshop Scenario Support

### Multi-Agent Coordination Examples

**Product Specifications After Purchase:**
- Query: "I ordered a MacBook last week, what ports does it have?"
- Flow: DB Agent finds customer's MacBook → RAG Agent retrieves specs from product document

**Return Eligibility:**
- Query: "Can I return the monitor I bought?"
- Flow: DB Agent finds monitor purchase with date → RAG Agent retrieves return policy rules

**Product Compatibility:**
- Query: "Will this monitor work with my Dell laptop?"
- Flow: DB Agent verifies customer owns Dell → RAG Agent retrieves compatibility_guide.md

**Bundle Recommendations:**
- Query: "I'm buying a laptop, what else should I get?"
- Flow: DB Agent analyzes purchase patterns → RAG Agent retrieves product descriptions

### HITL Scenarios

- Customer verification before showing order history
- Identity verification for returns and warranty claims
- Account requirements for order tracking

---

## Common Query Patterns

### Product Queries
- Specifications → Retrieve `TECH-XXX-###.md`, return Key Specifications section
- Compatibility → Retrieve product doc + potentially `compatibility_guide.md`
- Setup → Retrieve Setup & Getting Started section
- Troubleshooting → Retrieve Troubleshooting section (product-specific)

### Policy Queries
- Returns → Retrieve `return_policy.md`, apply rules based on product and date
- Warranty → Retrieve `warranty_guide.md`, determine coverage
- Shipping → Retrieve `shipping_guide.md` for timeframes

### Cross-Document Queries
- Return with refund calculation → DB (find purchase) + RAG (return policy rules)
- Compatibility check → DB (identify owned products) + RAG (compatibility guide)
- Bundle recommendations → DB (purchase patterns) + RAG (product descriptions)

---

## Data Quality Validation

### Completeness
- ✅ All 25 products have corresponding documents
- ✅ All 5 policy documents exist
- ✅ Filenames match product IDs exactly
- ✅ No contradictions between documents

### Consistency
- ✅ Product names, prices, and IDs match database
- ✅ Policy references consistent across all documents (return windows, fees, warranty terms)
- ✅ Contact information consistent
- ✅ Cross-references accurate

### Quality
- ✅ Specifications from real manufacturer sources
- ✅ Compatibility information accurate
- ✅ Setup instructions complete and actionable
- ✅ Troubleshooting provides specific solutions

---

## Tips for RAG Agent Usage

1. **Document Selection:** Use product_id for product docs, keywords like "return"/"warranty"/"shipping" for policy docs
2. **Section Targeting:** Each product doc has predictable sections (Specifications, Setup, Troubleshooting, etc.)
3. **Multi-Document Queries:** Some questions need multiple documents (e.g., return eligibility = product doc + return_policy.md)
4. **Policy Application:** Combine DB data (order date, price) with RAG policy rules for calculations
5. **Compatibility Guide:** Critical document for multi-product questions and setup scenarios

---

## Metadata

**Document Corpus:** TechHub RAG documents  
**Total Size:** ~360 KB (all markdown files)  
**Created:** October 2025  
**Purpose:** LangGraph Multi-Agent Workshop RAG source material  
**Status:** Production-ready, fully validated

For database documentation, see `../structured/SCHEMA.md`  
For generation process, see `../../data_generation/README.md`
