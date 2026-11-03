---
name: returns-and-warranty
description: Decide whether a TechHub purchase can be returned or covered under warranty, and explain the next step. Use for any return, refund-eligibility, defect, or warranty question.
---

# Returns and warranty

## Steps

1. Identify the product and, if the customer is verified, the order and its delivery date (ask the `order-specialist`).
2. Look up the governing terms with the `product-policy-specialist`: `policies/return_policy.md` for returns, `policies/warranty_guide.md` for defects.
3. Work out which case applies:
   - Within the return window: a return.
   - Outside the return window but a defect inside the warranty period: a warranty claim.
   - Neither: explain why, and offer the paid repair or support option if the policy lists one.
4. If the customer wants a refund on a delivered order, use `request_refund`. It pauses for human approval.

## Output

- One line with the verdict (return, warranty claim, or not eligible).
- The policy name and the specific term that decides it.
- The exact next step for the customer.
