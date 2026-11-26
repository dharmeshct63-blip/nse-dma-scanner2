#!/usr/bin/env python3
"""Send formatted daily 50-200 DMA strategy alerts via Gmail SMTP."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict


def build_html_report(scan_result: Dict) -> str:
    trade_date = scan_result.get("trade_date", "N/A")
    regime_ok = scan_result.get("regime_normal", True)
    capital = scan_result.get("portfolio_capital_inr", 500000)
    risk_pct = scan_result.get("risk_per_trade_pct", 0.5)
    risk_inr = scan_result.get("risk_budget_inr", 2500)
    breakouts = scan_result.get("breakouts", [])
    forming = scan_result.get("forming", [])

    regime_bg = "#dcfce7" if regime_ok else "#fef3c7"
    regime_fg = "#166534" if regime_ok else "#92400e"
    regime_txt = "Normal (100% Risk Budget)" if regime_ok else "Caution (50% Risk Cut)"

    bo_rows = ""
    for b in breakouts:
        bo_rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-weight:700;">{b['symbol']}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;">₹{b['close']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;color:#0284c7;font-weight:700;">₹{b['max_entry']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;color:#dc2626;font-weight:700;">₹{b['stop_loss']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;">₹{b['risk_per_share']:.2f}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;color:#059669;font-weight:700;">{b['qty']}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;">₹{b['position_value']:,.0f}</td>
          <td style="padding:8px;border-bottom:1px solid #e2e8f0;">{b['vol_mult']}x</td>
        </tr>
        """

    if not bo_rows:
        bo_rows = '<tr><td colspan="8" style="padding:12px;color:#64748b;">No confirmed 200 DMA breakouts today.</td></tr>'

    form_rows = ""
    for f in forming[:25]:
        roce = f.get("roce", "-")
        de = f.get("de", "-")
        form_rows += f"""
        <tr>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;font-weight:600;">{f['symbol']}</td>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;">₹{f['close']:.2f}</td>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;">₹{f['dma50']:.2f}</td>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;">₹{f['dma200']:.2f}</td>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;font-weight:700;">{f['ratio']:.3f}</td>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;">+{f['dist_to_200_pct']:.1f}%</td>
          <td style="padding:7px;border-bottom:1px solid #e2e8f0;">{roce}% / {de}</td>
        </tr>
        """

    if not form_rows:
        form_rows = '<tr><td colspan="7" style="padding:12px;color:#64748b;">No stocks in the 0.94–0.96 convergence zone today.</td></tr>'

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#0f172a;background:#f8fafc;padding:16px;">
      <div style="max-width:780px;margin:0 auto;background:#ffffff;border:1px solid #cbd5e1;border-radius:10px;padding:20px;">
        <h2 style="margin:0 0 8px 0;">50–200 DMA Daily Strategy Report ({trade_date})</h2>
        <div style="background:{regime_bg};color:{regime_fg};padding:10px 14px;border-radius:6px;font-size:13px;font-weight:700;margin-bottom:18px;">
          Regime: {regime_txt} &nbsp;|&nbsp; Capital: ₹{capital:,.0f} &nbsp;|&nbsp; Risk/Trade: {risk_pct}% (₹{risk_inr:,.0f})
        </div>

        <h3 style="margin:0 0 8px 0;font-size:15px;">Confirmed Breakout Signals (Enter Next Session Only if 9:16 AM Open &le; Max Entry)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;">
          <thead>
            <tr style="background:#f1f5f9;text-align:left;color:#475569;">
              <th style="padding:8px;">Symbol</th><th style="padding:8px;">Close</th><th style="padding:8px;">Max Entry (+1.5%)</th>
              <th style="padding:8px;">Stop-Loss</th><th style="padding:8px;">Risk/Sh</th><th style="padding:8px;">Qty</th>
              <th style="padding:8px;">Value</th><th style="padding:8px;">Vol</th>
            </tr>
          </thead>
          <tbody>{bo_rows}</tbody>
        </table>

        <h3 style="margin:0 0 8px 0;font-size:15px;">Forming Watchlist (Ratio 0.94–0.96, Rising 10D Slope)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:#f1f5f9;text-align:left;color:#475569;">
              <th style="padding:7px;">Symbol</th><th style="padding:7px;">Close</th><th style="padding:7px;">50 DMA</th>
              <th style="padding:7px;">200 DMA</th><th style="padding:7px;">Ratio</th><th style="padding:7px;">To 200 DMA</th>
              <th style="padding:7px;">ROCE / D:E</th>
            </tr>
          </thead>
          <tbody>{form_rows}</tbody>
        </table>
      </div>
    </body></html>
    """


def send_gmail_alert(scan_result: Dict) -> None:
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipient = os.environ.get("ALERT_RECIPIENT", gmail_user).strip()

    if not gmail_user or not gmail_pass:
        print("GMAIL_USER or GMAIL_APP_PASSWORD not set; skipping email delivery.")
        return

    bo_count = len(scan_result.get("breakouts", []))
    form_count = len(scan_result.get("forming", []))
    trade_date = scan_result.get("trade_date", "N/A")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[50-200 DMA] {bo_count} Breakout Signals & {form_count} Forming ({trade_date})"
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(build_html_report(scan_result), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, [recipient], msg.as_string())
    print(f"Sent strategy alert to {recipient}.")
