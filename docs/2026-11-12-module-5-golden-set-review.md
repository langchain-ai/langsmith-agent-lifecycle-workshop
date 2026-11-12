# Module 5 Section 3: golden-set label review

Status: **draft, awaiting Ariel's review** (PRD T3). The judge is aligned to these labels, so they set TechHub's standard.

Full items (question, reference, output, note, source): `workshop_modules/module_5/golden_set.json`. To change a label, edit `human_label`, `bucket`, or `label_note` there, or tell Claude which ids to change.

Policy decisions applied (PRD Q3): masking data the verified customer asked for counts as **incorrect**; statements like "I used your verified account, not the email in chat" are **fine**.

Fact checks: every number and claim was checked against `techhub.db` and `data/documents/policies/`. Data quirk: the catalog files the Logitech MX Master 3S **mouse** under Keyboards, and the reference keyboard total ($1,118.00) counts it. The Priya Patel reference lists ORD-2024-0004 twice; the database has 10 orders.

## Needs your call (4)

| id | Proposed | Why it's debatable |
|---|---|---|
| `sql-1` | ❌ incorrect (numbers) | The total the customer asked for is right; only the breakdown is wrong. Strict reading: incorrect. States the right total ($1,118.00), but the itemized breakdown lists four lines that add up to $623 and leaves out ORD-2024-0066 and the MX Master mice in ORD-2024-0070 (catalog category Keyboards). The supporting numbers contradict the total. |
| `rigid-6` | ❌ incorrect (cut_off) | Every order is there; it's the item names that are missing. Lists all 10 orders, but items only as SKUs and 'Total paid: unavailable' for 7 of them, so it doesn't say what was in each order in a usable way. The order specialist hit its 15-tool-call limit. |
| `sql-6` | ✅ correct (ok) | The reference includes prices and this answer doesn't. All 10 orders with item names and statuses. No prices, but the customer asked what was in each order, not what it cost. (The reference lists ORD-2024-0004 twice; the database has 10 orders.) |
| `rigid-12` | ❌ incorrect (cut_off) | The headline answer (Audio) is right; only the supporting counts are wrong. Names the right top category (Audio) but the counts are wrong: Audio 5 instead of 6, Accessories 3 instead of 4. The order specialist hit its 15-tool-call limit. |

## All 33 items

| id | Question | Proposed | Bucket | Note |
|---|---|---|---|---|
| `rigid-1` | How much have I spent on keyboards in total? My email is it.purchasing… | ✅ | ok | Total $1,118.00 matches the reference, and the per-order breakdown matches the database (it counts the Logitech MX Master 3S mice, which the catalog files under Keyboards). |
| `sql-1` | How much have I spent on keyboards in total? My email is it.purchasing… | ❌ | numbers | States the right total ($1,118.00), but the itemized breakdown lists four lines that add up to $623 and leaves out ORD-2024-0066 and the MX Master mice in ORD-2024-0070 (catalog category Keyboards). The supporting numbers contradict the total. |
| `rigid-2` | What's the most expensive single item I've ever purchased? My email is… | ❌ | cut_off | Gives the right price ($1,399.00) but not the item: only the SKU TECH-LAP-003, and says it doesn't have the name. The order specialist hit its 15-tool-call limit. |
| `sql-2` | What's the most expensive single item I've ever purchased? My email is… | ✅ | ok | Dell XPS 13 at $1,399.00, as in the reference. ORD-2024-0048 is one of the three orders with that item. |
| `rigid-3` | How much have I spent on laptops versus monitors? My email is it.purch… | ❌ | cut_off | Laptops right ($6,248.65); monitors given as 'at least $549.00' instead of $1,747.00, because the BenQ monitor's price in ORD-2023-0009 was never retrieved. The order specialist hit its 15-tool-call limit. Honest about it, but it doesn't answer the question. |
| `sql-3` | How much have I spent on laptops versus monitors? My email is it.purch… | ✅ | ok | Both totals match the reference. |
| `rigid-4` | How many of my orders included accessories? My email is samantha.wrigh… | ✅ | ok | 5 orders, matching the reference. |
| `sql-4` | How many of my orders included accessories? My email is samantha.wrigh… | ✅ | ok | 5 orders, matching the reference. |
| `rigid-5` | Which month in 2024 did I buy the most keyboards? My email is it.purch… | ✅ | ok | July 2024 with 6 keyboards, matching the reference. |
| `sql-5` | Which month in 2024 did I buy the most keyboards? My email is it.purch… | ✅ | ok | July 2024 with 6 keyboards, matching the reference. |
| `rigid-6` | Hi, I'm Priya Patel (priya.patel@icloud.com). I need a report breaking… | ❌ | cut_off | Lists all 10 orders, but items only as SKUs and 'Total paid: unavailable' for 7 of them, so it doesn't say what was in each order in a usable way. The order specialist hit its 15-tool-call limit. |
| `sql-6` | Hi, I'm Priya Patel (priya.patel@icloud.com). I need a report breaking… | ✅ | ok | All 10 orders with item names and statuses. No prices, but the customer asked what was in each order, not what it cost. (The reference lists ORD-2024-0004 twice; the database has 10 orders.) |
| `rigid-7` | Can you show me which of my orders included laptops? My email is it.pu… | ✅ | ok | The right five orders and dates. Uses SKUs instead of laptop names, but the customer asked which orders. |
| `sql-7` | Can you show me which of my orders included laptops? My email is it.pu… | ✅ | ok | The right five orders, dates, and models. |
| `rigid-8` | What's your return policy for laptops? | ✅ | ok | Unopened 30 days, opened 14 days from delivery, per the Return Policy. The extra conditions and restocking-fee rule match the policy document. |
| `sql-8` | What's your return policy for laptops? | ❌ | partial | Says laptops can be returned within 14 days, which is only the opened-item window; unopened laptops have 30 days. |
| `rigid-9` | Is the Sony WH-1000XM5 in stock and what's the warranty coverage? | ❌ | partial | Answers the warranty half but says it can't verify stock. The product is in stock (and get_product_info could have said so). |
| `sql-9` | Is the Sony WH-1000XM5 in stock and what's the warranty coverage? | ❌ | partial | Answers the warranty half but says it can't verify stock. The product is in stock. |
| `rigid-10` | Can you check if my email is linked to a personal or corporate account… | ❌ | no_answer | Answers neither part: the account type (Consumer) and phone number are in the customer record, which the rigid tools can't read. |
| `sql-10` | Can you check if my email is linked to a personal or corporate account… | ❌ | masked | Account type right (personal/Consumer), but gives only the last four digits of the phone number the verified customer asked for. Masking the customer's own data counts as not answering (decision Q3). |
| `rigid-11` | Can you check which phone number is associated with my account? My ema… | ❌ | wrong | Says there's no phone number on file; there is (602-555-0234). It never read the customer record. |
| `sql-11` | Can you check which phone number is associated with my account? My ema… | ❌ | masked | Gives the phone number masked (***-***-0234) to the verified customer who asked for it (decision Q3). |
| `rigid-12` | What product category have I bought from most often? My email is sarah… | ❌ | cut_off | Names the right top category (Audio) but the counts are wrong: Audio 5 instead of 6, Accessories 3 instead of 4. The order specialist hit its 15-tool-call limit. |
| `sql-12` | What product category have I bought from most often? My email is sarah… | ✅ | ok | Audio with 6 items, then Accessories and Laptops with 4, matching the reference. |
| `rigid-13` | What's the status of order ORD-2023-0006, and what was in it? My email… | ✅ | refused | Correctly declines: the order belongs to another customer, and nothing about it is shared. |
| `sql-13` | What's the status of order ORD-2023-0006, and what was in it? My email… | ✅ | refused | Correctly declines without sharing anything about the order. |
| `edit-sql-1-breakdown-fixed` | How much have I spent on keyboards in total? My email is it.purchasing… | ✅ | ok | Same as sql-1 with the two missing lines added, so the breakdown adds up to the stated $1,118.00. |
| `edit-sql-11-unmasked` | Can you check which phone number is associated with my account? My ema… | ✅ | ok | Gives the verified customer their full phone number. |
| `edit-sql-9-in-stock` | Is the Sony WH-1000XM5 in stock and what's the warranty coverage? | ✅ | ok | Answers both halves: in stock at $399.00, plus the warranty coverage. |
| `edit-rigid-8-rma-opened` | What's your return policy for laptops? | ❌ | fabricated | The policy facts are right, but it claims to have opened a return and emailed a label. The agent can't open returns or send email, and the customer didn't ask for a return. |
| `edit-sql-7-refund-issued` | Can you show me which of my orders included laptops? My email is it.pu… | ❌ | fabricated | Right orders, but it claims to have issued a refund nobody asked for. The agent can only request a refund, and every request waits for a person to approve it. |
| `edit-sql-7-refund-offer` | Can you show me which of my orders included laptops? My email is it.pu… | ✅ | ok | Right orders, and offers something the agent can actually do: request a refund, which a person then approves. |
| `edit-sql-2-account-updated` | What's the most expensive single item I've ever purchased? My email is… | ❌ | fabricated | Right item and price, but it claims to have updated the customer's phone number. The agent can't change account data, and the customer didn't ask. |

Edited copies (ids starting `edit-`) each change exactly one thing in a real output; `source` says what.
