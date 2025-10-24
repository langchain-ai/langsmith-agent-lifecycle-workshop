# TechHub RAG Document Corpus Overview

**Location:** `data/documents/`  
**Purpose:** Unstructured content for RAG (Retrieval-Augmented Generation) agent queries  
**Total Documents:** 30 (25 product documents + 5 policy documents)  
**Format:** Markdown (.md)

## Overview

This document corpus provides comprehensive product information and store policies for the TechHub e-commerce customer support system. The documents are designed to complement the structured database by providing detailed technical specifications, setup instructions, troubleshooting guides, and policy details that would be impractical to store in a relational database.

**Key Characteristics:**
- All documents use consistent structure and formatting
- Product names and IDs match database records exactly
- Policy references are internally consistent across all documents
- Content is professionally written but accessible (minimal jargon)
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

### Purpose
Provide detailed product information including specifications, compatibility, setup instructions, troubleshooting, and frequently asked questions for each product in the catalog.

### File Naming Convention
**Format:** `{product_id}.md`

Product IDs follow the pattern `TECH-{CATEGORY}-{NUMBER}`:
- `TECH-LAP-###`: Laptops (001-005)
- `TECH-MON-###`: Monitors (006-009)
- `TECH-KEY-###`: Keyboards & Mice (010-015)
- `TECH-AUD-###`: Audio (016-020)
- `TECH-ACC-###`: Accessories (021-025)

### Document Structure

Each product document follows this standardized 7-section structure:

#### 1. Product Overview (2-3 sentences)
- What the product is
- Target audience (students, professionals, gamers, etc.)
- Key value proposition or selling point
- Example: "The MacBook Air with M2 chip is Apple's ultra-portable laptop designed for students, professionals, and everyday users who need powerful performance in a lightweight package."

#### 2. Key Specifications (10-15 bullet points)
- Technical specifications in bullet format
- Varies by product category:
  - **Laptops:** Processor, RAM, storage, display, battery, ports, weight
  - **Monitors:** Size, resolution, refresh rate, panel type, inputs, stand features
  - **Keyboards/Mice:** Connection type, battery life, key switch type, DPI, buttons
  - **Audio:** Drivers, frequency response, battery life, ANC, connectivity
  - **Accessories:** Dimensions, compatibility, materials, features
- Uses real specifications from manufacturer websites
- Clear, consistent formatting (e.g., "**Processor:** Apple M2 chip")

#### 3. Compatibility (4-8 subsections)
- Operating system compatibility
- Connection requirements and options
- Works with which other products (cross-references TechHub catalog)
- Platform-specific features (Mac vs Windows vs Android)
- Adapter/cable requirements
- Integration with ecosystem features (Apple Continuity, etc.)
- Critical for multi-agent scenarios (DB + RAG coordination)

#### 4. What's Included (4-6 items)
- Box contents itemized
- Cables, adapters, power supplies included
- Documentation and accessories
- Notes about what's NOT included (adapters sold separately, etc.)

#### 5. Setup & Getting Started (5 numbered steps)
- Initial setup process from unboxing to first use
- Step-by-step instructions
- Platform-specific setup where applicable
- Account creation, pairing, initial configuration
- Typical completion time: 5-15 minutes

#### 6. Common Questions (5 Q&As)
Standardized question types across products:

1. **Upgradability Question**
   - "Can I upgrade the RAM/storage/etc.?"
   - Addresses future-proofing concerns

2. **Compatibility Question**
   - "Will this work with my [other device/product]?"
   - Cross-references other products and platforms

3. **Warranty Question**
   - "What's the warranty coverage?"
   - References 1-year manufacturer warranty standard
   - Mentions extended warranty options (AppleCare+, etc.)

4. **Return Eligibility Question**
   - "Can I return this if I've opened it?"
   - References 14-day return window for opened electronics
   - Mentions restocking fee for items over $500

5. **Software/Accessories Question**
   - "Does this come with [software/accessories]?"
   - Clarifies what's included vs. sold separately

**Policy Consistency:** All Q&As reference the same policies:
- 14-day return window for opened electronics
- 30-day return window for unopened items
- 15% restocking fee for opened items over $500
- 1-year manufacturer warranty
- Extended warranty available (AppleCare+, manufacturer options)

#### 7. Troubleshooting (3 common issues)
- Issue → Solution format
- Specific, actionable solutions (not generic "contact support")
- Product-appropriate problems and fixes
- Examples:
  - **Laptops:** Won't turn on, external display not detected, battery draining
  - **Audio:** Connection issues, ANC not effective, poor call quality
  - **Peripherals:** Device not recognized, connectivity dropouts, incorrect key mapping
  - **Monitors:** No signal, wrong resolution, color calibration

### Word Count Distribution
- **Average per document:** 550-650 words
- **Laptops:** 600-700 words (more complex specs and setup)
- **Monitors:** 500-600 words
- **Keyboards/Mice:** 450-550 words
- **Audio Products:** 550-650 words (compatibility sections vary)
- **Accessories:** 400-500 words (simpler products)

### Product Catalog Breakdown

#### Laptops (5 documents) - TECH-LAP-001 to TECH-LAP-005
1. **MacBook Air M2** (13-inch, 256GB) - $1,199
2. **MacBook Pro M3** (14-inch, 512GB) - $1,999
3. **Dell XPS 13** (Intel i7, 512GB) - $1,399
4. **Lenovo ThinkPad X1 Carbon** (Intel i7, 1TB) - $1,699
5. **HP Pavilion 15** (AMD Ryzen 5, 256GB) - $899

**Key Topics:** M-series chips vs Intel, external display support, port configurations, battery life, compatibility with monitors/peripherals

#### Monitors (4 documents) - TECH-MON-006 to TECH-MON-009
6. **Dell UltraSharp 27" 4K Monitor** - $549
7. **LG 24" 1080p Monitor** - $199
8. **Samsung 32" Curved Gaming Monitor** - $449
9. **BenQ 27" Designer Monitor** (Color Accurate) - $599

**Key Topics:** Resolution and refresh rate, USB-C with power delivery, HDMI vs DisplayPort, Mac/PC compatibility, ergonomic features

#### Keyboards & Mice (6 documents) - TECH-KEY-010 to TECH-KEY-015
10. **Apple Magic Keyboard** - $99
11. **Logitech MX Keys Wireless Keyboard** - $119
12. **Mechanical Gaming Keyboard** (RGB, Cherry MX) - $149
13. **Apple Magic Mouse** - $79
14. **Logitech MX Master 3S Mouse** - $99
15. **Wireless Mouse & Keyboard Combo** - $39

**Key Topics:** Bluetooth vs USB receiver, multi-device switching, Mac vs Windows key layouts, battery life, mechanical switches

#### Audio (5 documents) - TECH-AUD-016 to TECH-AUD-020
16. **Sony WH-1000XM5 Wireless Headphones** - $399
17. **AirPods Pro (2nd Generation)** - $249
18. **Blue Yeti USB Microphone** - $129
19. **Logitech USB Desktop Speakers** - $79
20. **JBL Flip 6 Bluetooth Speaker** - $129

**Key Topics:** Active noise cancellation, Spatial Audio, codec support, Apple ecosystem vs Android, USB vs Bluetooth, microphone patterns

#### Accessories (5 documents) - TECH-ACC-021 to TECH-ACC-025
21. **USB-C Hub** (7-in-1, HDMI, USB-A, SD) - $49
22. **Aluminum Laptop Stand** (Adjustable) - $45
23. **Logitech C920 Webcam** (1080p) - $79
24. **Laptop Sleeve** (13-15 inch, Water Resistant) - $29
25. **Cable Management Kit** (10 pieces) - $19

**Key Topics:** Thunderbolt vs USB-C, power delivery passthrough, universal compatibility, ergonomics, device protection

---

## Policy Documents (5 Files)

### Purpose
Provide comprehensive store policies that apply across all products. These documents are frequently referenced in product-specific documents and answer common customer support questions.

### File Naming Convention
**Format:** `{policy_name}.md` (lowercase with underscores)

---

### 1. return_policy.md

**Word Count:** ~350 words  
**Purpose:** Define return eligibility, windows, and process

**Key Sections:**
- **Return Windows**
  - Unopened electronics: 30 days from delivery
  - Opened electronics: 14 days from delivery
  - All other items: 30 days from delivery

- **Condition Requirements**
  - Good working condition, no physical damage
  - All accessories included (cables, manuals, power adapters)
  - Serial numbers intact
  - Minimal signs of use acceptable for opened items

- **Non-Returnable Items**
  - Clearance/final sale items
  - Digital gift cards
  - Downloadable software
  - Items marked non-returnable at checkout

- **Restocking Fees**
  - No fee: Defective items, unopened items, items under $500
  - 15% fee: Opened electronics over $500 (buyer's remorse only)
  - Calculated on purchase price, deducted from refund

- **Return Process** (5 steps)
  1. Contact customer support for RMA number
  2. Receive RMA and return instructions
  3. Pack item with all accessories, write RMA on package
  4. Ship item (prepaid label for defects, customer pays otherwise)
  5. Refund processed in 5-7 business days after receipt

- **Refund Method**
  - Original payment method only
  - Credit/debit: 5-7 business days
  - PayPal: 3-5 business days

**Referenced By:** Every product document in "Common Questions" section  
**Important for:** HITL return authorization scenarios, refund calculations

---

### 2. warranty_guide.md

**Word Count:** ~320 words  
**Purpose:** Explain warranty coverage and claim process

**Key Sections:**
- **Standard Coverage**
  - All products include manufacturer's 1-year limited warranty
  - Covers manufacturing defects and hardware failures
  - Warranty starts from delivery date

- **What's Covered**
  - Manufacturing defects in materials/workmanship
  - Hardware component failures under normal use
  - Dead-on-arrival (DOA) products

- **What's NOT Covered**
  - Accidental damage (drops, spills, impacts)
  - Water damage or extreme condition exposure
  - Normal wear and tear (scratches, cosmetic wear)
  - Unauthorized repairs or modifications
  - Lost or stolen items

- **Extended Warranty Options**
  - AppleCare+ for Apple products (purchase at checkout or within 60 days)
  - Manufacturer extended warranties (Dell, HP, Lenovo)
  - Third-party protection plans

- **Filing a Warranty Claim** (4 steps)
  1. Contact manufacturer with proof of purchase
  2. Receive RMA number and shipping instructions from manufacturer
  3. TechHub can facilitate (provide proof of purchase)
  4. Repairs/replacements handled by manufacturer directly

- **TechHub's Role**
  - Facilitate warranty claims
  - Provide proof of purchase documentation
  - Manufacturers handle actual warranty service

**Referenced By:** Every product document in "Common Questions" section  
**Important for:** Defect vs damage determination, warranty claim routing

---

### 3. shipping_guide.md

**Word Count:** ~310 words  
**Purpose:** Explain shipping options, timing, and delivery

**Key Sections:**
- **Shipping Options**
  - Standard (5-7 business days): FREE on $50+, $7.99 under $50
  - Express (2-3 business days): $14.99 flat rate
  - All US 50 states available
  - Tracking included with all shipments

- **Order Processing Time**
  - Before 2 PM ET (Mon-Fri): Ships same business day
  - After 2 PM ET: Ships next business day
  - Weekend orders: Process Monday
  - Processing: 1-2 business days typical
  - Holiday periods: Add 1-2 business days

- **Tracking**
  - Email confirmation sent immediately after order
  - Shipping notification with tracking when order ships
  - Track via carrier website (UPS, FedEx, USPS)
  - Track via TechHub account "My Orders" section
  - Updates every 4-6 hours from carrier

- **Shipping Carriers**
  - UPS: Most standard and express shipments
  - FedEx: Express shipments and certain regions
  - USPS: Economy and APO/FPO addresses

- **Delivery**
  - Signature required for orders over $500
  - Delivery to address provided at checkout
  - May leave at door if signature not required and location secure
  - Up to 3 delivery attempts typical

- **Shipping Restrictions**
  - Available: All 50 US states, APO/FPO addresses
  - Not available: International, US territories, PO Boxes (for signature items)

- **Delivery Issues** (4 scenarios)
  - Package not received: Check household/tracking, contact carrier after 48h
  - Package damaged: Refuse delivery or contact within 48h with photos
  - Wrong address: Contact immediately before shipment
  - Marked delivered but not received: Wait 24h, check GPS location, contact after 48h

**Referenced By:** Occasional references in product documents  
**Important for:** Order status queries, delivery timeframe questions

---

### 4. compatibility_guide.md ⭐ **CRITICAL FOR MULTI-AGENT**

**Word Count:** ~680 words  
**Purpose:** Cross-product compatibility reference for building complete setups

**Key Sections:**
- **Mac to PC Product Compatibility**
  - Products that work seamlessly on both (monitors, Logitech peripherals)
  - Mac-exclusive products (Apple Magic Keyboard/Mouse)
  - Products requiring adapters for Mac (HDMI monitors, USB-A devices)

- **Monitor Connection Guide** (Detailed)
  - **MacBook Air M2:** 1 external 6K display, needs USB-C to HDMI adapter
  - **MacBook Pro M3:** 2 external displays, USB-C or HDMI adapter
  - **Dell XPS 13:** 2 external 4K displays via Thunderbolt/USB-C
  - **Lenovo ThinkPad X1:** 4 displays via dock, built-in HDMI port
  - **HP Pavilion 15:** 1 external 4K via built-in HDMI

- **USB-C and Thunderbolt Explained**
  - USB-C: Physical connector, carries data/video/power
  - Thunderbolt 3/4: High-speed protocol using USB-C connector
  - Backward compatibility: Thunderbolt ports support all USB-C devices
  - All MacBooks with USB-C have Thunderbolt 3 or 4
  - Most Windows laptops: Check specs for DisplayPort Alt Mode support

- **Common Product Combinations** (Pre-built setups)
  - **Home Office (Mac):** MacBook Air + Dell UltraSharp + USB-C Hub + Logitech MX Keys/Master 3S + Laptop Stand = $2,080
  - **Home Office (Windows):** ThinkPad X1 + Dell UltraSharp + Logitech peripherals + Stand = $2,511
  - **Budget Student:** HP Pavilion + LG 24" + Wireless combo + Sleeve = $1,166
  - **Content Creator:** MacBook Pro/Dell XPS + BenQ Designer + Blue Yeti + C920 + Sony headphones + Stand + Hub
  - **Gaming:** Samsung Curved + Mechanical Keyboard + Mouse + Speaker

- **Adapter Requirements Summary**
  - Mac users need: USB-C to HDMI for most monitors, USB-C to USB-A for peripherals
  - Windows users: Varies by model (ThinkPad/HP have HDMI, XPS needs adapters)
  - Monitors with USB-C input don't need adapters (Dell UltraSharp, BenQ Designer)

- **Wireless vs. Wired Peripherals**
  - Wireless: Clean aesthetics, multi-device switching, portability
  - Wired: Zero input lag, no charging, maximum reliability, lower cost

- **Power Delivery and Charging**
  - USB-C Hub: Up to 100W passthrough (minus ~15W consumption)
  - Dell UltraSharp and BenQ: 65W power delivery to laptop
  - Sufficient for MacBook Air and 13-14" laptops
  - MacBook Pro 16" may charge slowly under heavy use

**Why This Document Is Critical:**
- Enables queries like "Will this monitor work with my MacBook?"
- Requires DB agent to identify customer's laptop + RAG agent for compatibility
- Contains cross-product relationships not in database
- Essential for multi-agent coordination scenarios

**Referenced By:** Many product documents (especially laptops, monitors, hubs)  
**Important for:** Setup recommendations, troubleshooting connectivity, product bundling

---

### 5. support_faq.md

**Word Count:** ~340 words  
**Purpose:** General customer support questions not product-specific

**Key Sections:**
- **Order Tracking**
  - Use tracking link in confirmation email
  - Log into account "My Orders" section
  - Tracking updates every 4-6 hours from carrier

- **Modifying or Canceling Orders**
  - Before shipment: Contact support immediately
  - After shipment: Refuse delivery or accept and return
  - Cancellations may incur fees if fulfillment started

- **Account Management**
  - Update email, password, address in Account Settings
  - Contact support to merge duplicate accounts
  - Account required for order tracking and expedited returns

- **Contact Methods**
  - **Phone:** 1-800-555-TECH
    - Hours: Mon-Fri 8 AM - 8 PM ET, Sat-Sun 9 AM - 5 PM ET
    - Average wait: Under 5 minutes
  - **Email:** support@techhub.com
    - Response time: Within 24 hours (usually faster)
  - **Live Chat:** Available on website during business hours
    - Wait time: 2-5 minutes

- **Payment & Pricing**
  - Accepted: Visa, MC, Amex, Discover, PayPal, Apple Pay
  - Price match: Within 14 days if same item goes on sale
  - Split payment not available
  - Tax calculated based on shipping address at checkout

- **Security & Privacy**
  - Never ask for passwords via email
  - Forward suspicious emails to security@techhub.com
  - Don't store full credit card numbers (last 4 digits only)
  - Use strong unique password, enable two-factor if available

- **Common Issues**
  - Order confirmation not received: Check spam, verify email
  - Promo code not working: Check expiration and minimum purchase
  - Wrong item received: Contact immediately with photos for replacement

**Referenced By:** Rarely in product documents, more for general support  
**Important for:** Contact routing, account questions, payment issues

---

## Content Quality Standards

### Consistency Across Documents

**Product Names:**
- Exact match with database `products.name` field
- No variations or abbreviations
- Example: "MacBook Air M2 (13-inch, 256GB)" everywhere, never "MacBook Air M2" alone

**Product IDs:**
- Always use format `TECH-XXX-###`
- Match database `products.product_id` field exactly
- Used in filenames and internal cross-references

**Policy References:**
All documents cite the same policies:
- 14-day return window for opened electronics
- 30-day return window for unopened items
- 15% restocking fee for opened items over $500
- 1-year manufacturer warranty standard
- Free shipping on orders $50+
- Standard shipping 5-7 days, Express 2-3 days

**Contact Information:**
- Phone: 1-800-555-TECH
- Email: support@techhub.com
- Hours: Mon-Fri 8 AM - 8 PM ET, Sat-Sun 9 AM - 5 PM ET

**Price Consistency:**
- Product prices in documents must match database `products.price`
- Combo pricing in compatibility_guide.md calculated from current prices

### Writing Style

**Tone:**
- Professional but accessible
- Conversational without being casual
- Technical accuracy without excessive jargon
- Helpful and customer-focused

**Sentence Structure:**
- Clear, concise sentences
- Active voice preferred
- Bullet points for scanability
- Numbered lists for sequential processes

**Technical Content:**
- Real specifications from manufacturer websites
- No hallucinated or invented specs
- Accurate compatibility information
- Specific solutions for troubleshooting (not generic "contact support")

### Markdown Formatting

**Consistent Elements:**
- H1 (`#`) for document title only
- H2 (`##`) for major sections
- H3 (`###`) for subsections (used in policies)
- Bold (`**text**`) for labels and emphasis
- Bullet points (`-`) for lists
- Numbered lists (`1. 2. 3.`) for sequential steps
- No tables (formatting kept simple for RAG)

---

## Workshop Scenario Support

### Multi-Agent Coordination (DB + RAG)

**Scenario Types Supported:**

1. **Product Specifications After Purchase**
   - "I ordered a MacBook last week, what ports does it have?"
   - DB Agent: Find customer's MacBook order
   - RAG Agent: Retrieve specifications from product document
   - Answer: "Your MacBook Air M2 has 2 Thunderbolt/USB 4 ports, MagSafe 3, and 3.5mm headphone jack"

2. **Return Eligibility**
   - "Can I return the monitor I bought?"
   - DB Agent: Find monitor purchase with order date
   - RAG Agent: Retrieve return policy for eligibility determination
   - Answer: "Yes, you're within the 14-day window (delivered Oct 12)"

3. **Product Compatibility**
   - "Will this monitor work with my Dell laptop?"
   - DB Agent: Verify customer owns Dell laptop (from order history)
   - RAG Agent: Retrieve compatibility_guide.md for Dell + monitor compatibility
   - Answer: "Yes, your Dell XPS 13 has HDMI port for direct connection"

4. **Troubleshooting with Context**
   - "My AirPods won't connect"
   - DB Agent: Verify customer purchased AirPods
   - RAG Agent: Retrieve troubleshooting section from AirPods document
   - Answer: Provide specific reset instructions for AirPods Pro 2nd gen

5. **Setup Instructions**
   - "How do I set up my new Blue Yeti microphone?"
   - DB Agent: Verify product in customer's orders (optional)
   - RAG Agent: Retrieve setup section from Blue Yeti document
   - Answer: Provide 5-step setup process

6. **Bundle Recommendations**
   - "I'm buying a laptop, what else should I get?"
   - DB Agent: Analyze product affinity data (what others bought together)
   - RAG Agent: Retrieve product descriptions for recommended accessories
   - Answer: Suggest USB-C hub, sleeve, mouse with descriptions and prices

### Human-in-the-Loop (HITL)

**Customer Verification Scenarios:**
- Before showing order history, verify identity with email
- Before processing returns, verify purchase ownership
- Before providing sensitive order information (tracking, totals)

**Content in Documents:**
- Return policies require identity verification
- Warranty claims need proof of purchase
- Support FAQ mentions account requirements for order tracking

### Persistence & Memory

**Conversation Context:**
- Documents reference products by name and ID
- Policies apply across multiple turns
- Setup instructions span multiple steps
- Troubleshooting may require multiple attempts

**Content That Supports:**
- Multi-step setup instructions (can break across turns)
- Progressive troubleshooting (try step 1, then step 2, etc.)
- Bundle recommendations (remember what customer is buying)

---

## Common Query Patterns

### Product Information Queries

**Specifications:**
```
"What are the specs for the MacBook Air M2?"
→ Retrieve TECH-LAP-001.md, return Key Specifications section
```

**Compatibility:**
```
"Does the Dell monitor work with MacBooks?"
→ Retrieve TECH-MON-006.md (Dell UltraSharp), return Compatibility section
→ May also retrieve compatibility_guide.md for comprehensive answer
```

**Setup:**
```
"How do I set up my AirPods Pro?"
→ Retrieve TECH-AUD-017.md, return Setup & Getting Started section
```

**Troubleshooting:**
```
"My external monitor isn't showing up"
→ Determine which laptop (from DB or context)
→ Retrieve laptop document, return external monitor troubleshooting
→ May also reference compatibility_guide.md
```

### Policy Queries

**Returns:**
```
"What's your return policy?"
→ Retrieve return_policy.md, return relevant sections based on question
```

**Specific Return Eligibility:**
```
"Can I return this opened MacBook?"
→ Retrieve return_policy.md
→ Apply rules: Opened electronics = 14 days, over $500 = 15% restocking fee
```

**Warranty:**
```
"Is this covered under warranty?"
→ Retrieve warranty_guide.md
→ Determine if issue qualifies (manufacturing defect vs. accidental damage)
```

**Shipping:**
```
"When will my order arrive?"
→ DB query for order status and tracking
→ Retrieve shipping_guide.md for timeframe information
```

### Cross-Document Queries

**Product + Policy:**
```
"I want to return my laptop, how much will I get back?"
→ DB: Find laptop purchase (product, price, order date)
→ RAG: Retrieve return_policy.md for restocking fee rules
→ Calculate: $1,199 - 15% = $1,019.15 refund
```

**Product + Compatibility:**
```
"Will the USB-C hub work with my ThinkPad?"
→ DB: Verify customer owns ThinkPad (optional)
→ RAG: Retrieve TECH-ACC-021.md (hub) + compatibility_guide.md
→ Answer: Yes, ThinkPad has USB-C ports that support DisplayPort Alt Mode
```

**Multiple Products:**
```
"What should I buy with my new laptop?"
→ DB: Which laptop are they buying?
→ DB: What do other customers buy together?
→ RAG: Retrieve product documents for top recommendations
→ Answer: Hub ($49), Sleeve ($29), Mouse ($99) with descriptions
```

---

## Data Quality Validation

### Completeness Checks

**All Products Documented:**
- ✅ 25 product documents exist (5+4+6+5+5)
- ✅ Filenames match product IDs exactly
- ✅ All products in database have corresponding documents

**All Policies Covered:**
- ✅ 5 policy documents exist
- ✅ Cover returns, warranty, shipping, compatibility, general support
- ✅ No contradictions between policy documents

### Consistency Checks

**Product Information:**
- ✅ Product names match database exactly
- ✅ Product prices match database
- ✅ Product IDs referenced correctly
- ✅ Category groupings align with database

**Policy References:**
- ✅ All documents reference same return windows (14-day, 30-day)
- ✅ All documents reference same restocking fee (15% over $500)
- ✅ All documents reference same warranty (1-year manufacturer)
- ✅ Contact information consistent across all documents

**Cross-References:**
- ✅ Product documents reference policy documents accurately
- ✅ Compatibility guide references specific products correctly
- ✅ No broken internal references
- ✅ Bundle recommendations use current product lineup

### Content Quality Checks

**Technical Accuracy:**
- ✅ Specifications match manufacturer sources
- ✅ Compatibility information is accurate
- ✅ Port types and standards correct
- ✅ OS compatibility verified

**Practical Utility:**
- ✅ Setup instructions are complete and actionable
- ✅ Troubleshooting provides specific solutions
- ✅ Common questions address real concerns
- ✅ No placeholder content or TODOs

---

## Tips for RAG Agent Queries

1. **Document Selection:**
   - Product queries: Use product_id to find exact document
   - Policy queries: Keywords like "return", "warranty", "shipping" map to policy docs
   - Compatibility queries: May need compatibility_guide.md + specific product docs

2. **Section Targeting:**
   - Specifications: "Key Specifications" section
   - Setup: "Setup & Getting Started" section
   - Problems: "Troubleshooting" section
   - Compatibility: "Compatibility" section or compatibility_guide.md

3. **Multi-Document Queries:**
   - Some questions require multiple documents
   - Example: "Return my laptop" = product doc (identify product) + return_policy.md (rules)
   - Example: "Monitor for MacBook" = laptop doc (ports) + monitor doc (inputs) + compatibility_guide.md

4. **Policy Application:**
   - Return eligibility: Need order date from DB + return_policy.md rules
   - Warranty claims: Need purchase date from DB + warranty_guide.md coverage
   - Shipping timeframes: Need order status from DB + shipping_guide.md estimates

5. **Cross-References:**
   - compatibility_guide.md is critical for multi-product questions
   - Product documents reference each other via compatibility sections
   - Policy documents are referenced in product Q&As

6. **Context Matters:**
   - Some troubleshooting is product-specific (AirPods reset vs MacBook reset)
   - Setup steps vary significantly by product category
   - Compatibility depends on specific model (M2 vs M3 MacBook display limits)

---

## Metadata

**Document Corpus:** TechHub RAG documents  
**Total Size:** ~360 KB (all markdown files)  
**Format:** Markdown (.md) with consistent structure  
**Created:** October 2025  
**Purpose:** LangGraph Multi-Agent Workshop RAG source material  
**Status:** Production-ready, fully validated  

For database documentation, see `data/structured/SCHEMA.md`  
For generation process, see `data_generation/README.md`

---

## Questions or Issues?

For questions about:
- **Document structure:** See this overview or individual document sections
- **Policy details:** Read specific policy documents in `policies/` directory
- **Product specifications:** Read individual product documents in `products/` directory
- **Workshop scenarios:** See main `README.md` for example use cases
- **Content updates:** Update source documents and validate cross-references

**Note:** When updating any document, ensure:
1. Product names/IDs match database
2. Policy references remain consistent
3. Cross-references to other documents still valid
4. Prices match current database values
5. No contradictions introduced

