import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import smtplib
import os
import io
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
import numpy as np

# ============================================================
# הגדרות — ערוך כאן את הרשימה שלך
# ============================================================

  ASSETS = [
    {"symbol": "TA35.TA",   "name": "מדד תל אביב 35"},
    {"symbol": "BANK5.TA",  "name": "מדד בנקים 5"},
    {"symbol": "KNST.TA",   "name": "קינסטון אינפרא"},
    {"symbol": "USDILS=X",  "name": "דולר/שקל"},
    {"symbol": "EURILS=X",  "name": "אירו/שקל"},
]

# כתובת המייל לשליחה ולקבלה
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "your@email.com")
SENDER_EMAIL    = os.environ.get("SENDER_EMAIL", "your@gmail.com")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")

# ============================================================
# שליפת נתונים
# ============================================================
def fetch_data(symbol):
    ticker = yf.Ticker(symbol)
    # שולפים שנה + כמה ימים קדימה כדי לוודא שיש מספיק נתונים
    hist = ticker.history(period="13mo")
    if hist.empty:
        return None
    return hist

def get_price_at(hist, target_date):
    """מחזיר את שער הסגירה הקרוב ביותר לתאריך נתון (לפני או באותו יום)"""
    hist_sorted = hist.sort_index()
    filtered = hist_sorted[hist_sorted.index.date <= target_date]
    if filtered.empty:
        return None
    return float(filtered['Close'].iloc[-1])

def build_report():
    today = datetime.today().date()
    dates = {
        "היום":       today,
        "לפני שבוע":  today - timedelta(days=7),
        "לפני חודש":  today - timedelta(days=30),
        "לפני שנה":   today - timedelta(days=365),
    }

    rows = []
    charts_data = {}  # לשמירת היסטוריה לגרפים

    for asset in ASSETS:
        symbol = asset["symbol"]
        name   = asset["name"]
        hist   = fetch_data(symbol)

        if hist is None:
            rows.append({"שם": name, "שגיאה": "לא נמצאו נתונים"})
            continue

        prices = {}
        for label, d in dates.items():
            prices[label] = get_price_at(hist, d)

        current = prices["היום"]
        if current is None:
            rows.append({"שם": name, "שגיאה": "אין שער היום"})
            continue

        def pct(old):
            if old is None or old == 0:
                return None
            return round((current - old) / old * 100, 2)

        # שמירת נתוני גרף — שנה אחורה
        hist_year = hist[hist.index.date >= (today - timedelta(days=365))]
        charts_data[name] = hist_year['Close']

        rows.append({
            "שם":              name,
            "שער היום":        round(current, 2)         if current             else "—",
            "לפני שבוע":       round(prices["לפני שבוע"], 2) if prices["לפני שבוע"] else "—",
            "לפני חודש":       round(prices["לפני חודש"], 2) if prices["לפני חודש"] else "—",
            "לפני שנה":        round(prices["לפני שנה"], 2)  if prices["לפני שנה"]  else "—",
            "שינוי יומי %":    pct(get_price_at(hist, today - timedelta(days=1))),
            "שינוי שבועי %":   pct(prices["לפני שבוע"]),
            "שינוי חודשי %":   pct(prices["לפני חודש"]),
            "שינוי שנתי %":    pct(prices["לפני שנה"]),
        })

    return pd.DataFrame(rows), charts_data

# ============================================================
# בניית גרפים
# ============================================================
def build_charts(df, charts_data):
    """מחזיר dict של שם -> PNG bytes"""
    chart_images = {}

    # צבעים
    COLOR_BG      = "#0d1117"
    COLOR_UP      = "#26a641"
    COLOR_DOWN    = "#f85149"
    COLOR_LINE    = "#58a6ff"
    COLOR_TEXT    = "#e6edf3"
    COLOR_SUBTEXT = "#8b949e"
    COLOR_GRID    = "#21262d"

    for _, row in df.iterrows():
        name = row["שם"]
        if "שגיאה" in row or name not in charts_data:
            continue

        series = charts_data[name].copy()
        if series.empty:
            continue

        pcts = {
            "יומי":   row.get("שינוי יומי %"),
            "שבועי":  row.get("שינוי שבועי %"),
            "חודשי":  row.get("שינוי חודשי %"),
            "שנתי":   row.get("שינוי שנתי %"),
        }

        fig = plt.figure(figsize=(10, 6), facecolor=COLOR_BG)
        gs  = gridspec.GridSpec(2, 1, height_ratios=[3, 1.2], hspace=0.45)

        # --- גרף עליון: קו מחיר ---
        ax1 = fig.add_subplot(gs[0])
        ax1.set_facecolor(COLOR_BG)

        x = series.index
        y = series.values

        ax1.plot(x, y, color=COLOR_LINE, linewidth=1.8, zorder=3)
        ax1.fill_between(x, y, alpha=0.15, color=COLOR_LINE, zorder=2)

        # הוסף נקודות ציון: שבוע, חודש, שנה
        today = datetime.today().date()
        milestones = {
            "לפני שבוע":  today - timedelta(days=7),
            "לפני חודש":  today - timedelta(days=30),
        }
        for label, d in milestones.items():
            closest = series[series.index.date <= d]
            if not closest.empty:
                ax1.axvline(x=closest.index[-1], color=COLOR_SUBTEXT,
                            linestyle="--", linewidth=0.8, alpha=0.6)
                ax1.text(closest.index[-1], ax1.get_ylim()[0],
                         label, color=COLOR_SUBTEXT, fontsize=7,
                         ha="center", va="bottom", rotation=45)

        ax1.set_title(name, color=COLOR_TEXT, fontsize=13, fontweight="bold", pad=10)
        ax1.tick_params(colors=COLOR_SUBTEXT, labelsize=8)
        ax1.spines[:].set_color(COLOR_GRID)
        ax1.yaxis.label.set_color(COLOR_SUBTEXT)
        ax1.grid(color=COLOR_GRID, linewidth=0.5, zorder=1)

        current_price = row.get("שער היום", "—")
        ax1.text(0.01, 0.97, f"שער נוכחי: {current_price}",
                 transform=ax1.transAxes, color=COLOR_TEXT,
                 fontsize=9, va="top", ha="left")

        # --- גרף תחתון: עמודות שינוי % ---
        ax2 = fig.add_subplot(gs[1])
        ax2.set_facecolor(COLOR_BG)

        labels = list(pcts.keys())
        values = [v if v is not None else 0 for v in pcts.values()]
        colors = [COLOR_UP if v >= 0 else COLOR_DOWN for v in values]

        bars = ax2.bar(labels, values, color=colors, width=0.5, zorder=3)
        ax2.axhline(0, color=COLOR_SUBTEXT, linewidth=0.8)

        for bar, val in zip(bars, values):
            sign = "+" if val >= 0 else ""
            ax2.text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + (0.1 if val >= 0 else -0.3),
                     f"{sign}{val:.1f}%",
                     ha="center", va="bottom" if val >= 0 else "top",
                     color=COLOR_TEXT, fontsize=8, fontweight="bold")

        ax2.set_title("שינוי באחוזים", color=COLOR_SUBTEXT, fontsize=9, pad=6)
        ax2.tick_params(colors=COLOR_SUBTEXT, labelsize=8)
        ax2.spines[:].set_color(COLOR_GRID)
        ax2.grid(color=COLOR_GRID, linewidth=0.5, axis="y", zorder=1)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    facecolor=COLOR_BG)
        plt.close(fig)
        buf.seek(0)
        chart_images[name] = buf.read()

    return chart_images

# ============================================================
# בניית מייל HTML
# ============================================================
def build_html(df, chart_images):
    today_str = datetime.today().strftime("%d/%m/%Y")

    def cell_color(val):
        if val is None or val == "—":
            return "#8b949e"
        try:
            v = float(val)
            if v > 0:  return "#26a641"
            if v < 0:  return "#f85149"
        except:
            pass
        return "#e6edf3"

    def fmt_pct(val):
        if val is None or val == "—":
            return "—"
        try:
            v = float(val)
            sign = "+" if v >= 0 else ""
            return f"{sign}{v:.2f}%"
        except:
            return str(val)

    table_rows = ""
    for _, row in df.iterrows():
        if "שגיאה" in row:
            table_rows += f"""
            <tr>
              <td style="padding:10px 14px;color:#e6edf3;font-weight:600">{row['שם']}</td>
              <td colspan="8" style="padding:10px 14px;color:#f85149">{row['שגיאה']}</td>
            </tr>"""
            continue

        cols = ["שינוי יומי %", "שינוי שבועי %", "שינוי חודשי %", "שינוי שנתי %"]
        pct_cells = "".join(
            f'<td style="padding:10px 14px;text-align:center;color:{cell_color(row.get(c))};font-weight:700">'
            f'{fmt_pct(row.get(c))}</td>'
            for c in cols
        )

        table_rows += f"""
        <tr style="border-bottom:1px solid #21262d">
          <td style="padding:10px 14px;color:#e6edf3;font-weight:600;white-space:nowrap">{row['שם']}</td>
          <td style="padding:10px 14px;text-align:center;color:#58a6ff;font-weight:700">{row.get('שער היום','—')}</td>
          <td style="padding:10px 14px;text-align:center;color:#8b949e">{row.get('לפני שבוע','—')}</td>
          <td style="padding:10px 14px;text-align:center;color:#8b949e">{row.get('לפני חודש','—')}</td>
          <td style="padding:10px 14px;text-align:center;color:#8b949e">{row.get('לפני שנה','—')}</td>
          {pct_cells}
        </tr>"""

    # גרפים מוטמעים
    charts_html = ""
    for name, img_bytes in chart_images.items():
        b64 = base64.b64encode(img_bytes).decode()
        charts_html += f"""
        <div style="margin:24px 0">
          <img src="data:image/png;base64,{b64}"
               style="width:100%;max-width:700px;border-radius:12px;border:1px solid #21262d" />
        </div>"""

    html = f"""
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:'Segoe UI',Arial,sans-serif;direction:rtl">
  <div style="max-width:780px;margin:0 auto;padding:32px 16px">

    <!-- כותרת -->
    <div style="margin-bottom:28px">
      <h1 style="margin:0;color:#e6edf3;font-size:22px;font-weight:700">
        📈 דוח שוק ההון — {today_str}
      </h1>
      <p style="margin:6px 0 0;color:#8b949e;font-size:13px">
        נתוני בורסת תל אביב | נשלח אוטומטית
      </p>
    </div>

    <!-- טבלה -->
    <div style="border-radius:12px;overflow:hidden;border:1px solid #21262d;margin-bottom:32px">
      <table style="width:100%;border-collapse:collapse;background:#161b22;font-size:13px">
        <thead>
          <tr style="background:#21262d">
            <th style="padding:12px 14px;text-align:right;color:#8b949e;font-weight:600">נייר</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">היום</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">לפני שבוע</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">לפני חודש</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">לפני שנה</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">יומי %</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">שבועי %</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">חודשי %</th>
            <th style="padding:12px 14px;text-align:center;color:#8b949e;font-weight:600">שנתי %</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>

    <!-- גרפים -->
    <h2 style="color:#e6edf3;font-size:16px;margin-bottom:16px">📊 גרפים</h2>
    {charts_html}

    <!-- פוטר -->
    <p style="margin-top:32px;color:#484f58;font-size:11px;text-align:center">
      הדוח נוצר אוטומטית • נתונים מיאהו פיננסים • לא ייעוץ השקעות
    </p>
  </div>
</body>
</html>"""
    return html

# ============================================================
# שליחת מייל
# ============================================================
def send_email(html_content, subject):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

# ============================================================
# נקודת כניסה ראשית
# ============================================================
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] שולף נתונים...")
    df, charts_data = build_report()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] בונה גרפים...")
    chart_images = build_charts(df, charts_data)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] בונה מייל...")
    today_str = datetime.today().strftime("%d/%m/%Y")
    html = build_html(df, chart_images)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] שולח מייל...")
    send_email(html, f"📈 דוח שוק ההון — {today_str}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ הדוח נשלח בהצלחה!")

if __name__ == "__main__":
    main()
