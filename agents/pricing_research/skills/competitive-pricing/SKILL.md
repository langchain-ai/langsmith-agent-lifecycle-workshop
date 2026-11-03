---
name: competitive-pricing
description: Produce a competitive pricing report comparing TechHub's catalog prices against current market prices, with flagged products and recommendations. Use when asked to benchmark prices, review pricing, or recommend price changes.
---

# Competitive pricing report

## Steps

1. Get our current prices for the requested products or category from the `catalog-analyst`.
2. For each product, ask the `market-researcher` for current prices at 3+ major US retailers (for example Amazon, Best Buy, the manufacturer's store), with URLs and whether each is a sale price.
3. For each product compute: market median, our price, and the gap (`(ours - median) / median`).
4. Flag products more than 5% above or 10% below the median.
5. Write the report to `/reports/<category>_pricing.md`.

## Report format

| Product | Our price | Market median | Gap | Flag | Sources |
|---|---|---|---|---|---|

Sources are citation numbers, e.g. `[1][2][3]`.

Then:
- **Recommendations:** one line per flagged product (raise, lower, hold), with the reason.
- **Watch list:** promotions or model refreshes that could move prices soon.
- **Sources:** `### Sources`, one line per number: `[1] Retailer - product: URL`.

Only recommend; changes go through `propose_price_change` and need approval.
