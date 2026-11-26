# 50–200 DMA Convergence Strategy (₹0/Month Self-Hosted)

Automated daily NSE swing-trading scanner that runs on **GitHub Actions** (your PC stays off), stores historical Bhavcopy data in your private repository, filters by your **Screener.in** fundamentals CSV, and sends a formatted **Gmail** report every trading day at **4:30 PM IST**.

## Folder Structure
- `.github/workflows/daily_scanner.yml` — Scheduled Mon–Fri 4:30 PM IST (`11:00 UTC`) runner + manual backfill trigger.
- `config.yaml` — All strategy rules (0.94–0.96 ratio, 10-day slopes, fundamental thresholds, 1.5% gap rule, 0.5% risk sizing).
- `src/fetch_nse_bhavcopy.py` — NSE UDiFF Bhavcopy downloader & parser.
- `src/scanner.py` — Technical + fundamental convergence & breakout engine.
- `src/email_alert.py` — Mobile-friendly HTML email sender via Gmail SMTP.
- `src/run_daily.py` — Main orchestrator (`--backfill-days`, `--dry-run`).
- `data/screener_fundamentals.csv` — Replace this with your quarterly Screener.in CSV export.

---

## 10-Minute Setup Guide

### 1. Create a Private GitHub Repo
1. Go to GitHub and create a **Private** repository (e.g., `nse-dma-scanner`).
2. Upload all files from this ZIP into the repository (preserving folders like `.github/workflows/`).

### 2. Add Your Gmail Secrets
1. In your Google Account, enable **2-Step Verification** and create a 16-character **App Password** (Security → App passwords).
2. In your GitHub repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `GMAIL_USER`: your Gmail address (e.g., `you@gmail.com`)
   - `GMAIL_APP_PASSWORD`: your 16-character App Password (no spaces)
   - `ALERT_RECIPIENT`: email address to receive daily alerts (can be the same as `GMAIL_USER`)
   - `PORTFOLIO_CAPITAL` *(optional)*: e.g., `500000` (defaults to `config.yaml` value)

### 3. Upload Your Screener.in Export
1. Run your fundamental query on [Screener.in](https://www.screener.in/) (`Market cap >= 300`, `Sales growth 3Years > 10`, `Profit growth 3Years > 12`, `ROCE > 15`, `ROE > 12`, `Debt to equity < 0.5`, `Cash from operations > 0`, `Pledged percentage = 0`).
2. Export to CSV and replace `data/screener_fundamentals.csv` in your repo (refresh once per quarter).

### 4. Seed 220+ Days of History (One-Time)
1. Go to **Actions → Daily 50-200 DMA Scanner → Run workflow**.
2. Set `backfill_days` to `340` (calendar days ≈ 230+ trading sessions) and click **Run workflow**.
3. Once complete, the scanner will run automatically every weekday at **4:30 PM IST** at **₹0/month**.
