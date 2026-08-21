"""南港展覽館展覽時程查詢 & 當前停車費率報告（HTML 輸出）"""

import re
import webbrowser
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 設定 ──────────────────────────────────────────────
EVENT_URL = "https://www.tainex.com.tw/event"
PARKING_URL = "https://www.tainex.com.tw/service/transportation/parking-garage"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}
HTML_FILE = Path(__file__).parent / "tainex_report.html"


# ── 展覽時程 ──────────────────────────────────────────
def fetch_exhibitions() -> list[dict]:
    """從官網抓取展覽時程列表。"""
    resp = requests.get(EVENT_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[dict] = []
    # 展覽卡片連結格式: /event/{id}
    for link in soup.find_all("a", href=re.compile(r"/event/\d+")):
        text = link.get_text(separator=" ", strip=True)
        if not text:
            continue

        # 嘗試解析展覽名稱、館別、日期
        hall_match = re.search(r"([12]館)", text)
        date_match = re.search(
            r"(\d{4})\s*(\d{2}/\d{2})\s*\([一二三四五六日]\)\s*[-–]\s*(\d{2}/\d{2})\s*\([一二三四五六日]\)",
            text,
        )
        # 清理名稱：移除館別標記、日期區段
        name = text.split("地點")[0].strip()
        name_clean = re.sub(
            r"^[\s\d館]*\d{4}\s*\d{2}/\d{2}\s*\([一二三四五六日]\)\s*[-–]\s*\d{2}/\d{2}\s*\([一二三四五六日]\)\s*",
            "", name,
        ).strip()
        name_clean = re.sub(r"^[12]館\s*", "", name_clean).strip()

        location = ""
        loc_match = re.search(r"地點[：:]\s*(.+)", text)
        if loc_match:
            location = loc_match.group(1).strip()

        events.append(
            {
                "name": name_clean or text[:60],
                "hall": hall_match.group(1) if hall_match else "",
                "year": date_match.group(1) if date_match else "",
                "start": date_match.group(2) if date_match else "",
                "end": date_match.group(3) if date_match else "",
                "location": location,
                "url": link["href"] if link["href"].startswith("http") else "https://www.tainex.com.tw" + link["href"],
            }
        )

    # 去重 (同一 url 只保留一筆)
    seen: set[str] = set()
    unique: list[dict] = []
    for e in events:
        if e["url"] not in seen:
            seen.add(e["url"])
            unique.append(e)
    return unique


# ── 停車費 ──────────────────────────────────────────
def fetch_parking_info() -> dict[str, str]:
    """抓取停車場收費文字，回傳 {區塊名稱: 完整收費文字}。"""
    resp = requests.get(PARKING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 整段收費文字
    body_text = soup.get_text(separator="\n", strip=True)

    sections: dict[str, str] = {}
    # 擷取 1 館與 2 館停車辦法
    for label, pattern in [
        ("1館", r"(台北南港展覽館1館\s*地下停車場.+?)(?=台北南港展覽館2館|$)"),
        ("2館", r"(台北南港展覽館2館\s*地下停車場.+?)(?=周邊停車場|南港展覽館1館\s*\n|$)"),
    ]:
        m = re.search(pattern, body_text, re.DOTALL)
        if m:
            sections[label] = re.sub(r"\s+", " ", m.group(1)).strip()

    return sections


# ── HTML 報告 ──────────────────────────────────────────
def _extract_rates(text: str) -> dict[str, str]:
    """從停車費文字中擷取每小時費率數字。"""
    rates: dict[str, str] = {}
    m = re.search(r"非展覽期間[^：]*：.*?(\d+)分鐘至.*?停車費[^\d]*(\d+)元.*?每增加半小時加收(\d+)元.*?每日[^\d]*(\d+)元", text)
    if m:
        rates["非展覽_首小時"] = m.group(2)
        rates["非展覽_半小時"] = m.group(3)
        rates["非展覽_每日上限"] = m.group(4)
    m = re.search(r"展覽期間[^：]*：.*?每小時(\d+)元.*?每增加半小時加收(\d+)元", text)
    if m:
        rates["展覽_每小時"] = m.group(1)
        rates["展覽_半小時"] = m.group(2)
    m = re.search(r"過夜停車費(\d+)元", text)
    if m:
        rates["過夜"] = m.group(1)
    return rates


def _is_expo_today(hall: str, events: list[dict]) -> tuple[bool, list[str]]:
    """判斷今天該館是否為展覽期間，回傳 (是否展覽中, 展覽名稱列表)。"""
    today = datetime.now().date()
    ongoing: list[str] = []
    for e in events:
        if not e["year"] or not e["start"] or not e["end"]:
            continue
        # 館別比對：hall 為 "1館" 或 "2館"，e["hall"] 可能包含 "1館"
        if hall not in e.get("hall", ""):
            continue
        try:
            year = int(e["year"])
            s_m, s_d = e["start"].split("/")
            e_m, e_d = e["end"].split("/")
            start = datetime(year, int(s_m), int(s_d)).date()
            end = datetime(year, int(e_m), int(e_d)).date()
            if start <= today <= end:
                ongoing.append(e["name"])
        except (ValueError, TypeError):
            continue
    return bool(ongoing), ongoing


def generate_html(events: list[dict], parking: dict[str, str]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 展覽表格
    rows = ""
    for i, e in enumerate(events, 1):
        date_str = f"{e['year']} {e['start']} ~ {e['end']}" if e["start"] else "未定"
        hall = e["hall"] or "-"
        loc = e["location"] or "-"
        name_link = f'<a href="{e["url"]}" target="_blank">{e["name"]}</a>'
        rows += f"<tr><td>{i}</td><td>{name_link}</td><td>{hall}</td><td>{date_str}</td><td>{loc}</td></tr>\n"

    # 停車費詳情
    parking_html = ""
    for hall_name, text in sorted(parking.items()):
        # 以句號或▪分段顯示
        formatted = re.sub(r"(▪)", r"<br><b>\1", text)
        formatted = re.sub(r"(。)", r"\1<br>", formatted)
        parking_html += f"<h3>🏢 {hall_name}</h3><div class='parking-detail'>{formatted}</div>"

    # 停車費摘要卡片 — 依展覽排程判斷目前適用費率
    summary_boxes = ""
    for hall_name in ["1館", "2館"]:
        if hall_name not in parking:
            continue
        r = _extract_rates(parking[hall_name])
        is_expo, expo_names = _is_expo_today(hall_name, events)
        overnight = r.get("過夜", "?")

        if is_expo:
            period_label = "展覽期間"
            period_color = "#e74c3c"
            period_bg = "#fdecea"
            price = r.get("展覽_每小時", "?")
            price_unit = "元 / 每小時"
            half_hr = r.get("展覽_半小時", "?")
            daily_max = "依展覽調整"
            detail = f"超過1小時每半小時 +{half_hr}元"
            expo_info = "、".join(expo_names[:3])
            status_html = f'<div style="margin-top:8px;font-size:13px;color:#c0392b;">📌 進行中: {expo_info}</div>'
        else:
            period_label = "非展覽期間"
            period_color = "#27ae60"
            period_bg = "#eafaf1"
            price = r.get("非展覽_首小時", "?")
            price_unit = "元 / 首小時"
            half_hr = r.get("非展覽_半小時", "?")
            daily_max = r.get("非展覽_每日上限", "?") + "元"
            detail = f"超過1小時每半小時 +{half_hr}元"
            status_html = '<div style="margin-top:8px;font-size:13px;color:#27ae60;">📌 目前無展覽</div>'

        summary_boxes += f"""<div class="summary-box">
  <h3>🏢 {hall_name}</h3>
  <div class="period-badge" style="background:{period_bg};color:{period_color};display:inline-block;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:bold;margin-bottom:10px;">{period_label}</div>
  <div class="rate-highlight">
    <div class="rate-card">
      <div class="label">目前費率</div>
      <div class="price" style="color:{period_color};">${price}</div>
      <div class="unit">{price_unit}</div>
    </div>
    <div class="rate-card">      <div class="label">每日上限</div>
      <div class="price" style="font-size:22px;color:#e67e22;">{daily_max}</div>
      <div class="unit"></div>
    </div>
    <div class="rate-card">      <div class="label">過夜費</div>
      <div class="price" style="font-size:22px;color:#666;">${overnight}</div>
      <div class="unit">元（逾晚間10時）</div>
    </div>
  </div>
  <div class="rate-detail">{detail}</div>
  {status_html}
</div>\n"""

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>南港展覽館監控報告</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Microsoft JhengHei', 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; padding: 20px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ text-align: center; color: #1a5276; margin-bottom: 5px; }}
  .timestamp {{ text-align: center; color: #888; margin-bottom: 25px; font-size: 14px; }}
  .card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 20px; }}
  .card h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #3498db; color: #fff; padding: 10px 12px; text-align: left; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #f5faff; }}
  a {{ color: #2980b9; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .parking-detail {{ background: #f9f9f9; padding: 14px; border-radius: 6px; margin-bottom: 12px; line-height: 1.8; font-size: 14px; }}
  .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .summary-box {{ background: #f5f8ff; border: 1px solid #d4e3f5; border-radius: 8px; padding: 16px; }}
  .summary-box h3 {{ color: #2c3e50; margin-bottom: 12px; font-size: 16px; }}
  .rate-highlight {{ display: flex; gap: 12px; margin-bottom: 10px; }}
  .rate-card {{ flex: 1; text-align: center; background: #fff; border-radius: 8px; padding: 12px 8px; border: 1px solid #e0e0e0; }}
  .rate-card .label {{ font-size: 12px; color: #888; margin-bottom: 4px; }}
  .rate-card .price {{ font-size: 28px; font-weight: bold; }}
  .rate-card .unit {{ font-size: 12px; color: #666; }}
  .rate-detail {{ font-size: 13px; color: #666; line-height: 1.6; }}
  h3 {{ margin: 14px 0 8px; color: #2c3e50; }}
  ul {{ margin: 8px 0 8px 20px; }}
</style>
</head>
<body>
<div class="container">
  <h1>🏛️ 南港展覽館監控報告</h1>
  <div class="timestamp">報告產生時間：{now}</div>

  <div class="card">
    <h2>🅿️ 停車費率摘要</h2>
    <div class="summary-grid">
      {summary_boxes}
    </div>
  </div>

  <div class="card">
    <h2>📅 近期展覽時程（共 {len(events)} 場）</h2>
    <table>
      <tr><th>#</th><th>展覽名稱</th><th>館別</th><th>日期</th><th>地點</th></tr>
      {rows}
    </table>
  </div>

  <div class="card">
    <h2>📋 停車場收費標準（完整）</h2>
    {parking_html}
  </div>
</div>
</body>
</html>"""

    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"📄 HTML 報告已產生: {HTML_FILE}")


# ── 主程式 ──────────────────────────────────────────
def main() -> None:
    events = fetch_exhibitions()
    parking = fetch_parking_info()
    generate_html(events, parking)
    webbrowser.open(HTML_FILE.as_uri())


if __name__ == "__main__":
    main()
