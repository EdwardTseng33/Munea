# Billing Credit Rules — Visual QA

Date: 2026-07-14
Viewport: 390 × 844 (mobile)

## Sources

- Reference: `C:\Users\ADMINI~1\AppData\Local\Temp\codex-clipboard-ac125644-12d4-4630-8423-6a9188a2f441.png`
- Subscription implementation: `C:\Users\Administrator\.codex\visualizations\2026\07\13\019f5ce6-53dd-79e0-bd98-a264dcc195fd\billing-plan-mobile.png`
- Point-purchase implementation: `C:\Users\Administrator\.codex\visualizations\2026\07\13\019f5ce6-53dd-79e0-bd98-a264dcc195fd\billing-points-mobile.png`
- Side-by-side comparison: `C:\Users\Administrator\.codex\visualizations\2026\07\13\019f5ce6-53dd-79e0-bd98-a264dcc195fd\billing-credit-qa-comparison.png`

## Checks

- Subscription page keeps the selected reference hierarchy, segmented controls, plan cards, colors, radii, spacing, and typography.
- The monthly allowance and purchased-credit rules appear directly below the monthly/yearly selector in a distinct information card.
- The point-purchase page repeats the accumulation, post-expiry retention, and deduction-order rules below the purchase button.
- Both tabs, monthly/yearly control, plan selection, point-pack selection, purchase CTA, and close control remain interactive.
- No clipped labels, horizontal overflow, overlapping controls, or undersized primary actions were observed at the checked viewport.
- Copy is plain-language and consistent across the UI and billing source-of-truth document.

## Comparison history

1. Initial pass matched the layout but the new rule container was visually too close to the page background.
2. Increased surface contrast, added the existing product shadow token, used mint icon wells, and cache-busted the stylesheet.
3. Re-captured both tabs and confirmed the final rule cards remain readable without crowding the plan or point-pack choices.

final result: passed
