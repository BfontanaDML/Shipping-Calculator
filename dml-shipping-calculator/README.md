# DML Shipping Calculator (v1.5.0)

An internal tool for DML staff. The calculator opens directly, with no sign-in. The screen works in three steps:

1. **Shipment.** Choose the product (Caps, Toques, EK9, EK12, EK60), enter the quantity, then choose the UPS service: **UPS World Ease Standard** or **UPS Worldwide Expedited/Saver**.
2. **Boxes.** The tool suggests the fewest physical boxes. Staff can change box sizes, box counts and pieces per box, and can enter measured weights.
3. **Price.** Enter the **Discounted UPS Total Cost (CAD)**: DML's discounted Total Cost for the complete shipment, every box included, as shown in DML's signed-in UPS quote. The tool shows the **Customer Shipping Price** and the **Shipping Price Per Piece**. The **How to Get Shipping Prices** button next to the field opens step-by-step UPS instructions, including the DML UPS login.

The tool does not connect to UPS and needs no database.

> **Staff only.** The DML UPS user ID and password are written into the app's instructions (`templates/index.html`).
> Anyone who can open the calculator, or read the repository, can see them.
> Keep the GitHub repository **private**, and share the calculator's URL with DML staff only.

---

## Run it on a Mac

You need Python 3.9 or newer. Check with `python3 --version`.

```bash
cd dml-shipping-calculator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5050**. Press `Ctrl+C` to stop.

## Put it on GitHub (upload team)

1. Unzip the file. Everything inside the `dml-shipping-calculator` folder is the repository.
2. On github.com, click **New repository**. Name it `dml-shipping-calculator`, choose **Private** (required), and do not add a README. Then click **Create repository**.
3. Choose **uploading an existing file**. Drag in the **contents** of the `dml-shipping-calculator` folder (not the folder itself), and click **Commit changes**.
   On a Mac, Finder hides `.gitignore`; press `Cmd+Shift+.` to show it so it gets uploaded too.

Or, from Terminal:

```bash
cd dml-shipping-calculator
git init && git add . && git commit -m "DML Shipping Calculator v1.5.0"
git branch -M main
git remote add origin https://github.com/<your-org>/dml-shipping-calculator.git
git push -u origin main
```

The repository contains the DML UPS login (in the instructions), so it must stay **private**. Give access only to the people who maintain the app.

## Deploy on Render (Web Service)

In Render, click **New → Web Service**, connect the private GitHub repository, and enter:

| Setting | Value |
|---|---|
| Language / Runtime | **Python 3** |
| Branch | `main` |
| Root Directory | *(leave blank)* |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2` |
| Health Check Path (Advanced) | `/healthz` |
| Instance Type | any (Free works for testing) |

**Environment variables: none are required.** Render provides `PORT` itself, and there are no UPS or sign-in settings to configure.
These are optional:
- `DML_TOOLS_HOME_URL`: makes "DML Tools" in the header a link to your tools home page.
- `PYTHON_VERSION`: pins Python, for example `3.12.7`. The app works on Python 3.9 to 3.13.

Click **Create Web Service**. Render builds the app and gives it a URL, for example `https://dml-shipping-calculator.onrender.com`.

The calculator opens directly. Anyone with the URL can see it, including the DML UPS login in **How to Get Shipping Prices**, so share the URL with DML staff only.
When someone with access leaves, change the UPS password: update it in `templates/index.html`, commit, and Render redeploys automatically.

## Check the deployed app

1. Open `https://<your-app>.onrender.com/healthz`. It should show `{"ok": true, "app_version": "1.4.0", ...}`.
2. Open `https://<your-app>.onrender.com/`. The calculator should open directly, with no sign-in.
3. Run this test:
   - **Caps**, quantity **150**, **UPS World Ease Standard**;
   - Boxes should show **1 × 24 × 19 × 20 (144 pcs)** and **1 × 11 × 9 × 8 (6 pcs)**, 2 boxes, 72 lb quote weight;
   - Discounted UPS Total Cost **100** should give a **Customer Shipping Price of $125.00 CAD** and a **Shipping Price Per Piece of $0.83**.
4. Click **How to Get Shipping Prices**. The **eight** steps, with the DML UPS user ID and password in step 1 and the UPS account-number step as step 6, should appear. Click it again to close.
5. Clear the Discounted UPS Total Cost. The price should change back to "—", never $0.00.

## How the numbers work

- **Price:** `Customer Shipping Price = Discounted UPS Total Cost × 1.25`. That is a 25% markup on the entered cost. The entered amount already includes DML's UPS discount, so the calculator applies no other discount.
  - `Shipping Price Per Piece = Customer Shipping Price ÷ quantity`, rounded to the cent. It is shown to 4 decimals when it is under one cent, for example $0.0042.
  - Example: $100.00 → $125.00. Only the two results are shown on screen.
- **Discounted UPS Total Cost** must be more than $0 with at most 2 decimals. Commas and a `$` sign are accepted.
- **Boxes:** the suggestion always uses the fewest physical boxes. Among options with that many boxes, it picks the lowest total dimensional weight. Identical boxes are grouped into one row, so 30,000 EK60 is shown as 555 + 1 boxes. Limits are 1 to 100,000 pieces and up to 50 rows.
- **Weights (UPS World Ease Standard):**
  - Dimensional weight per box = L × W × H ÷ 139 (whole inches), rounded up.
  - Quote weight per box = the higher of the dimensional weight and the measured weight rounded up.
- **UPS Worldwide Expedited/Saver:** boxes are suggested, but no calculated weight is shown. Staff use the billable weight on the UPS quote.

Source data, capacities and workbook findings are documented in `AUDIT.md`.

## Change the packing data

Box sizes, capacities and pricing rates are in **`data/shipping_config.json`**.
Edit it, change `config_version`, commit to GitHub, and Render redeploys automatically.
The app checks the file when it starts and will not start if a value is invalid.

## Tests (for developers)

```bash
python -m unittest discover -s tests             # automated tests
pip install playwright && python -m playwright install chromium
python tests/ui_check.py                         # optional browser check, desktop + phone
```

Test output never prints the UPS password.

## Files

```
app.py                     web app and routes (/, /healthz, /api/*)
shipping/                  packing, weights, pricing, data-file validation
data/shipping_config.json  editable box, capacity and pricing data
templates/, static/        the employee screen (templates/index.html holds the UPS instructions and login)
tests/                     automated tests and browser check
AUDIT.md                   source-data audit (workbook cells, formulas, open questions)
CHANGELOG.md               version history
```
