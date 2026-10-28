# Workbook audit — Shipping Calculator.xlsx

Audited 2026-10-07 for DML Shipping Calculator v1.0.0; updated for v1.1.0 and v1.2.0
(see `CHANGELOG.md`). This file is the technical record of the source data and formulas.
None of it is shown on the employee screen. Cell references are `Sheet!Cell`. Only product data, box data and
pricing formulas were transferred into the app (`data/shipping_config.json`).
Nothing else from the workbook is in this package.

## 0. Product names vs workbook sheets

| Employee-facing product | Workbook sheet the data came from |
|---|---|
| Caps | `Caps` |
| Toques | `TK3` |
| EK9 | `EK9` |
| EK12 | `EK12` |
| **EK60** | **`EK64`** |

The **EK60** product's capacities and box rules come from the workbook sheet named
**`EK64`** (cells `EK64!D6:D11`), unchanged. "EK64" is not used anywhere in the app.
It appears in this audit only as the name of that source sheet. The sheet
references below (`EK64!…`) therefore describe EK60 data.

## 1. Security: carrier login details in the workbook

The workbook has free-text cells that appear to hold carrier sign-in details or
contact addresses. I found these cells by searching for keywords and did not
read or copy their contents. They are **not** in the code, data file, tests,
screenshots, logs or ZIP.

| Sheet | Cells flagged |
|---|---|
| UPS Calculator | B15–B18, B31, B35 (notes block B13:B35) |
| Puro Calc | B4–B10 |
| FedEx Calc | B6–B10, C18 |
| Q | B26 (address used by the mailto link in Q!B30) |

**Recommendation:** remove these details from the workbook and change those
passwords, because the file has been shared. The app does not log in to any carrier.

**v1.4.0:** at DML's explicit request, the DML UPS user ID and password are written directly into
the "How to Get Shipping Prices" instructions (`templates/index.html`, and as test expectations in
`tests/`). They are therefore part of the repository and visible to anyone who can open the app.
From v1.5.0 the app opens without any sign-in, at DML's request. DML must keep the GitHub
repository private and share the URL with DML staff only. The app never writes the login to logs.

## 2. Pricing formula

| Item | Workbook | App |
|---|---|---|
| Formula | `'UPS Calculator'!J10` (same pattern in J16, J22, J28, J34, J40 and columns K–N): `=((Service+Fuel)*(1-C2))/(1-C3)+C4` | v1.4.0: `Customer Shipping Price = Discounted UPS Total Cost × 1.25`. The PM enters DML's already-discounted UPS Total Cost, so the app applies **no** discount of its own. |
| Meaning of 25% (`C3`) | Divides by 0.75, so it is a 25% **margin** on the selling price | 25% **markup on cost**, as specified |
| Discount (`C2` = 40%) | Applied inside the formula | Not applied (v1.4.0). The UPS amount entered is already DML's discounted cost. |
| $100.00 entered | (workbook would discount it first) | **$125.00** |
| `C4` "Extra" | Flat adder, currently 0 | Not implemented (see decision D6) |
| Per piece | `J11 =J10/C7` etc. gives `#DIV/0!` when quantity is blank | Never divides without a valid quantity. Shows "incomplete" and no price. |

**Currency rounding (app):** Decimal arithmetic. The customer shipping price and the
per-piece amount are rounded to the cent (round half up).
Per-piece is also shown to 4 decimals in the internal detail. If cent rounding
would give $0.00 per piece (very large orders), 4 decimals are shown everywhere,
for example 30,000 pcs at $125.00 → $0.0042.

## 3. Quantity lookups (product sheets)

Each product sheet looks up weight with
`=INDEX(I5:I29, MATCH(qty, D5:D29) + (LOOKUP(qty, D5:D29)<>qty))`
(e.g. `Caps!N5`, and in 'UPS Calculator'!K7:N7, J13:N13, K19:N19, K25:N25, J31:N31, K37:N37).
An approximate `MATCH` needs ascending breakpoints. The sheets break that rule:

| Problem | Cells |
|---|---|
| Out-of-order breakpoints | `EK64!D8`=9 after `D7`=12; `EK64!D14`=63 after `D13`=66; `D20`=117 after `D19`=120; `D26`=171 after `D25`=174 |
| Duplicate breakpoints | `EK52!D7`=`D8`=12, `D13`=`D14`=84, `D19`=`D20`=156, `D25`=`D26`=228, `D31`=`D32`=300 |
| Sample box listed twice (qty 1 and qty 6) | rows 5 and 6 on every product sheet |
| Range stops at 4 master cartons | Caps 577+, Toques 1,729+, EK60 217+ (sheet `EK64`) return `#REF!` |
| Range mismatch | `'UPS Calculator'!J31:M31` use rows 5–29 of EK52, `N31` uses 5–35 |
| Combination rows are sums, not cartons | `C12:C29` ("6+1"… "6+6+6+6") add quantity and weight of separate boxes |

Recalculating the sheet formula (LibreOffice; Excel can differ on unsorted data,
which is the problem) gives, for example:

| Input | Workbook result | Why it is wrong |
|---|---|---|
| EK60 (sheet `EK64`), 8–12 pcs | 7 lb (catalog box, "12") | The 23 × 9 × 7 box holds only 9 EK60 |
| EK60 (sheet `EK64`), 61–66 pcs | 73 lb (master + catalog) | Same catalog box conflict |
| EK60 (sheet `EK64`), 63 pcs | 73 lb | Breakpoint 63 is skipped by the binary search |
| Caps, 577 pcs | `#REF!` | No row above 4 master cartons |

**App rule instead:** packing uses only the physical boxes and verified per-box
capacities (see README). It works for any quantity up to 100,000, gives the same
result every time and never uses the combination rows as cartons.

## 4. Box dimensions and weights

**v1.1.0 change:** the app now **calculates** dimensional weight from each box's
approved whole-inch dimensions with the UPS Canada non-air rule: L × W × H ÷ **139**,
rounded **up** to the next whole pound. The workbook's own weights are kept only as
historical data (`workbook_est_weight_lb` in the data file) and are never used or shown.

| Box | Workbook dims | App dims | Volume | **App dimensional weight (v1.1)** | Workbook weight (historical) | Note |
|---|---|---|---|---|---|---|
| Sample | `Caps!F6:H6` 11 × 9 × 8 | 11 × 9 × 8 | 792 in³ | **6 lb** (5.70 ↑) | 6 | same |
| Catalog / cap | `Caps!F7:H7` 13 × 11 × 7 | 13 × 11 × 7 | 1,001 in³ | **8 lb** (7.20 ↑) | 7 | workbook rounded to nearest |
| "2 Doz" | `Caps!F8` = **22.8** × 9 × 7 | **23** × 9 × 7 (approved) | 1,449 in³ | **11 lb** (10.42 ↑) | 10 | workbook rounded to nearest; 22.8 in gives 10.33, also 11 rounded up |
| "4 Doz" | `Caps!F9:H9` 24 × 10 × 14 | 24 × 10 × 14 | 3,360 in³ | **25 lb** (24.17 ↑) | 24 | workbook rounded to nearest |
| "6 Doz" | `Caps!F10:H10` 24 × 10 × 20 | 24 × 10 × 20 | 4,800 in³ | **35 lb** (34.53 ↑) | 35 | same |
| "12 Doz" master | `Caps!F11:H11` 24 × 19 × 20 | 24 × 19 × 20 | 9,120 in³ | **66 lb** (65.61 ↑) | 66 | same |

Source for the rule: UPS Canada, *Package Dimensions, Size Limits and Weight Guide*
(ups.com/ca): round each measurement up to the next whole number; divisor 139 for
non-air shipments in inches/pounds; increase any fraction to the next whole pound.

**Measured weight and quote weight (v1.1.0; shown as "Quote weight" from v1.2.0).** A PM may enter the actual measured
weight per box. It is rounded up to the next whole pound and shown separately from the
dimensional weight. The **quoting weight per box = max(dimensional weight, rounded-up measured
weight)**. A low measured weight never lowers it below the dimensional weight. With no
measurement, the quote weight equals the dimensional weight.

**Service selection (v1.2.0).** The screen offers **UPS World Ease Standard** and **UPS Worldwide
Expedited/Saver**. The calculated weights above apply to **UPS World Ease Standard** only.
For **UPS Worldwide Expedited/Saver** (air), UPS Canada uses a divisor of 115 for domestic air (it would give
7 / 9 / 13 / 30 / 42 / 80 lb), and international air follows separate rules. The app does
**not** calculate air dimensional weight. It hides the calculated weights and shows one short line
telling staff to use the billable weight on the UPS quote. Packing and
pricing still work.

Other findings:

- The workbook weights (product sheets, column I) are ÷ 139 **rounded to the nearest pound**. `Packaging Specs!G5:G11` show the unrounded values. This is why three of them (7 / 10 / 24) are 1 lb below the UPS figures.
- `Packaging Specs!H5:H8` divide by 166, an older divisor. `Packaging Specs!I5:I21` ("FEDEX / UPS", 2016) list different, lower weights (for example 7 for "2 Doz" and 55 for "12 DOZ"). They look like actual scale weights. `'UPS Calculator'!P38:P39` say the side tables show **actual** weights. Neither is used. Measured weights are now entered per quote instead.
- `Packaging Specs!B5`/`B6` describe the small boxes as "10x8x7 … 1-6 pcs" and "12x10x6 … 7-12pcs". These may be inside dimensions. The outside dimensions 11 × 9 × 8 and 13 × 11 × 7 are used.
- `Packaging Specs!C8` (2 Doz Import 22.5 × 8 × 8) and the "Import", "Vernon" and other 12-Doz rows (`C12:E28`) are other cartons. They are not used.

## 5. Capacities

The four principal boxes match the approved release table on every product sheet
(rows 8–11, column D). Status in the app: **approved**, used for automatic suggestions.

The sample box (row 6 = 6) and catalog box (row 7 = 12) have the **same capacity
on every product sheet**, including Toques (72 in the 23 × 9 × 7 box) and EK60
(sheet `EK64`; 9 in the 23 × 9 × 7 box). This looks like a template copied across sheets, not a
measurement for each product.

| Product | Sample 11 × 9 × 8 (wb 6) | Catalog 13 × 11 × 7 (wb 12) | Evidence | App status |
|---|---|---|---|---|
| Caps | 6 | 12 | Named "Catalog/ Cap Box". `Packaging Specs!A3:B6` list both under CAPS for 1–6 and 7–12 pcs. Volume check (24 caps in 1,449 in³): about 13 and 17 fit. | **Audited, auto-suggested** |
| Toques | 6 | 12 | Generic value; volume suggests far more fit (≈39 / ≈50) | **Not confirmed**: manual only, flagged |
| EK9 | 6 | 12 | Generic value (volume ≈20 / ≈25) | **Not confirmed**: manual only, flagged |
| EK12 | 6 | 12 | Generic value. Catalog 12 is close to the volume limit (≈12.4). | **Not confirmed**: manual only, flagged |
| EK60 (sheet `EK64`) | 6 | 12 | 12 in the catalog box is more than the 9 that fit the larger 23 × 9 × 7 box (`EK64!D8`). Sample 6 is above the ≈4.9 volume share. | **Conflict: blocked** (not selectable) |

Volume comparisons are only a plausibility check, not proof of fit.

Other capacity notes:

- `Caps!E8` = 28 and `EK12!E8` = 24 ("Up to") are not explained. The app uses column D (24 and 18). See decision D5.
- `'UPS Calculator'!P5:Z33` has older box tables (masks, KN95, Caps, knits). The "Caps" table lists 23 × 15 × 23 at 144 pcs / 66 lb as the "Cap America mastercarton" and 20 × 20 × 16 as the "Overseas mastercarton". Both conflict with `Caps!F11:H11` (24 × 19 × 20). They are not used.
- `Packaging Specs!A34:E41` (2 dz / 4 dz / 6 dz / MC per style) agree with the approved capacities for tk3, ek9, ek12 and ek64.
- The EK52 sheet exists but EK52 is not in this release.

## 6. Hard-coded or stale values in 'UPS Calculator'

| Cell | Value | Issue |
|---|---|---|
| J7 | 10 | Caps W1 weight typed over the lookup formula (K7:N7 are formulas) |
| J19 | 1005 | EK9 W1 typed over the formula. 1,005 lb is not plausible. |
| J25 | 35 | EK12 W1 typed over the formula |
| J37 | 300 | W1 for the `EK64` sheet (EK60 product) typed over the formula |
| C10 | 80 | Leftover EK12 quantity; together with J26 = 2,943.57 and J27 = 23.31 it produces $29.67/pc in `Q!C14` |
| J8, J14, K14, J20, J27, K27, J38 | various | Leftover service/fuel amounts from earlier quotes |
| Q!B28 | `#VALUE!` | File-name formula error in the email helper |

## 7. Out of scope

`Puro Calc`, `FedEx Calc` and `Zone Average` were not used (this release is UPS
with manual pricing). The `Q` sheet's layout ("UPS Standard, 3 to 5 working days",
"NET price in $CAD") informed the customer-facing labels in v1.0–1.1. The customer summary was removed in v1.2.0.

## 8. Decisions requested from DML

These do not block use of the app. The defaults below are already built in, and
each can be changed in `data/shipping_config.json` without code changes.

| # | Question | Current default |
|---|---|---|
| D1 | Confirm Caps fit 6 in the sample box and 12 in the catalog box | Auto-suggested for Caps |
| D2 | Measured capacities of the sample and catalog boxes for Toques, EK9, EK12 | Manual only, flagged "capacity not confirmed" |
| D3 | Can EK60 go in the sample or catalog box at all, and how many? | Blocked |
| D4 | ~~Keep the workbook's nearest-pound weights or use UPS round-up?~~ | **Resolved in v1.1.0:** UPS round-up (8 / 11 / 25 lb). The workbook values are historical only. |
| D5 | What do the "Up to" values `Caps!E8`=28 and `EK12!E8`=24 mean? | Ignored |
| D6 | Is the "Extra" adder `'UPS Calculator'!C4` still needed? | Not implemented |
| D7 | ~~Should an alternative arrangement be offered?~~ | **Resolved in v1.2.0:** no. One suggestion, always the fewest boxes. |
| D8 | Should a later version calculate air dimensional weight (domestic ÷ 115, international rules)? | Out of scope. Calculated weights are hidden for UPS Worldwide Expedited/Saver. |
