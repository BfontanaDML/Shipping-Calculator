# Change log

## 1.5.0 — 2026-10-07

- **How to Get Shipping Prices:** new step 6, "Under **How will you pay the shipping charges?**, choose DML’s UPS account number from the **Select a UPS Account Number** dropdown, then click **Update**." The instructions now have eight steps. The panel is still closed by default, and the DML UPS login is still shown in step 1.
- **Sign-in removed:** the `DML_ACCESS_PASSWORD` / `DML_ACCESS_USER` staff password, its start-up warning and its Render setup steps are gone. The calculator opens directly, and Render needs no environment variables. Keep the GitHub repository private and share the URL with DML staff only.
- **README:** the Git commit example now says v1.5.0. The deployment check now says the app opens directly and that the instructions have eight steps.
- **Unchanged:** products, box suggestions and pricing (`Discounted UPS Total Cost × 1.25`, so $100 → $125.00).
- **Tests:** 65 automated tests and 118 browser checks on desktop and phone. They cover the 8-step order with step 6 in place, the app opening with no sign-in, and $100 → $125.00.


## 1.4.0 — 2026-10-07

**Pricing**
- The PM now enters DML's **discounted** UPS Total Cost, which already includes DML's UPS discount. The calculator's 40% discount is removed everywhere: the code, the data file (`dml_discount_rate`), the tests and the docs.
- `Customer Shipping Price = Discounted UPS Total Cost × 1.25` (a 25% markup on the entered cost) and `Shipping Price Per Piece = Customer Shipping Price ÷ quantity`. For example, $100.00 → **$125.00**, and $0.83 per piece for 150 pieces. The calculation stays hidden; the only results shown are Customer Shipping Price and Shipping Price Per Piece.
- The input is renamed **Discounted UPS Total Cost (CAD)** and is still the only price field. Its missing-value message is "Enter the discounted UPS total cost."

**How to Get Shipping Prices**
- The DML UPS user ID and password are now written directly into step 1 of the instructions, at DML's request. The `UPS_LOGIN_USER_ID` and `UPS_LOGIN_PASSWORD` environment variables are removed, so Render needs no UPS settings.
- The steps are reworded: sign in; Shipping → Calculate Shipping Cost; Cap America as origin; destination postal code and $1 customs value; every package from Step 2; the Step 1 service; copy the discounted Total Cost into Step 3. The panel is still closed by default.

**Access**
- The GitHub repository must be private, because it now contains the UPS login.
- The README makes `DML_ACCESS_PASSWORD` an explicit step in the Render setup. The app logs a start-up warning if it is not set, and the warning never includes the login.

**Tests**
- The automated tests and browser checks now cover: $100 → $125.00 only; the markup-only formula; no discount; the new label and messages; the login shown in the instructions with no environment variables; staff access; and that the login is not in the API, scripts, logs or test output.


## 1.3.0 — 2026-10-07

**Step 3: one UPS price field**
- The UPS service cost and fuel surcharge fields are replaced by one field, **UPS Total Cost (CAD)**: the Total Cost UPS shows for the complete shipment, with every box included.
- Pricing (superseded in 1.4.0): `UPS Total Cost × 0.60 × 1.25`. The calculation stays hidden. The only results shown are Customer Shipping Price and Shipping Price Per Piece.
- Validation: the field is required and must be more than $0, with at most 2 decimals; commas and `$` are accepted. Errors appear beside the field, and a missing or invalid amount shows "—", never $0.00.
- API: `POST /api/quote` now takes `ups_total_cost`. `ups_service_cost` and `ups_fuel_surcharge` are no longer used.

**How to Get Shipping Prices**
- A small button next to the field opens 7-step UPS instructions. It is closed by default. Step 1 links to the UPS website (opens in a new tab).
- The DML UPS login was shown inside step 1, read from Render environment variables (replaced in 1.4.0). The page is sent with `Cache-Control: no-store`.

**Staff-only access**
- New optional `DML_ACCESS_PASSWORD` (and `DML_ACCESS_USER`, default `dml`): when set, the browser asks for a staff user name and password before showing any page. `/healthz` stays open for Render.
- If the UPS login is set without a staff password, a startup warning goes to the Render log. The warning never includes the login values.
- The README now says the GitHub repository must be private and the deployed app restricted to DML staff, and gives the Render settings.

**Tests**
- 65 automated tests and 112 browser checks (desktop and phone). They cover the single field, the pricing formula of that version, validation, the instructions panel (closed by default, opens, 7 steps, link, login display), staff access, and that no password appears in logs. The tests use made-up login values only.


## 1.2.0 — 2026-10-07 (simplified employee screen)

**Screen**
- One screen in three steps: **Shipment** (product → quantity → UPS service), **Boxes**, **Price**.
- UPS service choices are now **UPS World Ease Standard** and **UPS Worldwide Expedited/Saver**. The separate service-name field is gone.
- The only pricing results are **Customer Shipping Price** and **Shipping Price Per Piece**. The discount, cost, markup and formula breakdown are no longer on screen. The calculation then was `(service + fuel) × 0.60 × 1.25` (superseded in 1.4.0).
- Input errors are short and appear beside the field they belong to. Messages about missing values only appear after the employee reaches that field. An incomplete or invalid quote shows "—", never $0.00.
- The phone layout shows each box row as a compact card.

**Removed**
- Quote details (reference / prepared by), the multi-quantity price grid, the customer summary, the internal detail view, quote-record downloads and the Box data & audit page. Formulas and source notes are now in `README.md` and `AUDIT.md` only.
- The alternative packing arrangement. The app always suggests the fewest boxes.
- The large weight-guidance panel, the freight / large-shipment warning and the other warning panels. Large orders still work, with no carton cutoff.

**Kept from v1.1.0**
- Products, box dimensions, capacities, grouped box rows, quantity validation (1–100,000), and the 50-row limit.
- World Ease Standard weights: dimensional weight (÷ 139, rounded up), measured weight, and quote weight (the greater of the two, measured rounded up).
- Expedited/Saver: the packing is shown, calculated weights are hidden, and one short line says to use the UPS quote's billable weight.

**Handoff**
- The README now covers running on a Mac, uploading to GitHub, the exact Render Web Service settings, environment variables (none required) and checking the deployed app.
- The ZIP contains only source code, data, tests and docs. There is no workbook, credentials, virtual environment, cache, screenshots or test output.
- API: `POST /api/quote` replaces `/api/evaluate`, `/api/evaluate-line` and `/api/record`.


## 1.1.0 — 2026-10-07

**Product name**
- EK64 is renamed **EK60** everywhere employees or customers see it: product buttons, quote cards, customer summary, internal detail, downloadable quote records, data page, screenshots and README. The product id is now `ek60`, and `ek64` is no longer accepted.
- Capacities and box rules are unchanged (9 / 18 / 27 / 54; sample and catalog boxes still blocked).
- The audit states that EK60 data comes from the workbook sheet named `EK64` (AUDIT §0).

**Dimensional weight (UPS non-air)**
- Dimensional weight is now calculated from each box's whole-inch dimensions: L × W × H ÷ 139, rounded up to a whole pound. 13 × 11 × 7 = **8 lb**, 23 × 9 × 7 = **11 lb**, 24 × 10 × 14 = **25 lb** (6, 35 and 66 lb are unchanged).
- The workbook's 7 / 10 / 24 lb figures are kept only as historical audit data (`workbook_est_weight_lb`, shown on the data page as "historical, not used").
- Packing choices and the alternative arrangement use the new weights.

**Measured weight and quoting guidance**
- Each row shows **dimensional weight**, optional **measured weight** and **quoting weight** separately (all per box).
- Measured weight is rounded up to a whole pound. Quoting weight = the greater of dimensional weight and rounded-up measured weight. A low measured weight never reduces it.
- Totals show both the dimensional weight and the quoting weight.

**Large orders and limits**
- Identical boxes are grouped into one row with a **Boxes** count. 30,000 EK60 is 2 rows / 556 boxes, and 100,000 pieces of any product works.
- The old 500-box cap is replaced by an enforced limit of 50 box **rows** per quantity (suggestions use 1–3 rows). The 100,000-piece limit is unchanged and enforced.
- Over 100 boxes shows a note to confirm small-package vs freight with UPS.
- Per piece is shown to 4 decimals when cent rounding would show $0.00 (30,000 pcs at $75.00 → $0.0025).

**Air services**
- New **UPS service type** choice: Non-air (default) or Air. Weight guidance is limited to non-air. With Air selected, weight columns show "n/a (air)" and staff use the UPS air quote's billable weight.
- The app warns if a non-air quote has an air-sounding service name (Express, Saver, Air…).

**Unchanged**
- Manual UPS service price and fuel surcharge inputs.
- Pricing: `(service + fuel) × 0.60 × 1.25`, so $90 + $10 → $75.00.

**Records and tests**
- The quote record is now `record_schema` 2: per-row count and pieces per box; dimensional, measured and quoting weights; service type; and the weight rules.
- Tests: 68 unit/API tests, including EK60 30,000 end to end, and 45 browser checks.

## 1.0.0 — 2026-10-07
- First release.
