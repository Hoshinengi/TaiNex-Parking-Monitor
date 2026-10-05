"""南港展覽館展覽時程 & 停車費率 — Flet Android App"""

import calendar
import json
import re
import threading
from datetime import datetime, date
from pathlib import Path

import flet as ft
import requests
from bs4 import BeautifulSoup

# ── 設定 ──────────────────────────────────────────────
EVENT_URL = "https://www.tainex.com.tw/event"
PARKING_URL = "https://www.tainex.com.tw/service/transportation/parking-garage"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Mobile Safari/537.36"
    )
}


# ── 資料擷取 ──────────────────────────────────────────
def fetch_exhibitions() -> list[dict]:
    resp = requests.get(EVENT_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[dict] = []
    for link in soup.find_all("a", href=re.compile(r"/event/\d+")):
        text = link.get_text(separator=" ", strip=True)
        if not text:
            continue

        hall_matches = re.findall(r"([12]館)", text)
        hall_str = " ".join(sorted(set(hall_matches)))
        date_match = re.search(
            r"(\d{4})\s*(\d{2}/\d{2})\s*\([一二三四五六日]\)\s*[-–]\s*(\d{2}/\d{2})\s*\([一二三四五六日]\)",
            text,
        )
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

        events.append({
            "name": name_clean or text[:60],
            "hall": hall_str,
            "year": date_match.group(1) if date_match else "",
            "start": date_match.group(2) if date_match else "",
            "end": date_match.group(3) if date_match else "",
            "location": location,
            "url": link["href"] if link["href"].startswith("http") else "https://www.tainex.com.tw" + link["href"],
        })

    seen: set[str] = set()
    unique: list[dict] = []
    for e in events:
        if e["url"] not in seen:
            seen.add(e["url"])
            unique.append(e)
    return unique


def fetch_parking_info() -> dict[str, str]:
    resp = requests.get(PARKING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    body_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))

    sections: dict[str, str] = {}
    for label, pattern in [
        ("1館", r"南港1館｜停車收費(.+?)(?=南港2館｜停車收費)"),
        ("2館", r"南港2館｜停車收費(.+?)(?=繳費方式)"),
    ]:
        m = re.search(pattern, body_text)
        if m:
            sections[label] = m.group(1).strip()
    return sections


def extract_rates(text: str) -> dict[str, str]:
    rates: dict[str, str] = {}
    m = re.search(r"一般臨停 (\d+) 元／小時 當日最高 (\d+) 元", text)
    if m:
        rates["一般_每小時"], rates["一般_每日上限"] = m.groups()
    m = re.search(r"一般臨停計費.*?每增加半小時加收 (\d+) 元", text)
    if m:
        rates["一般_半小時"] = m.group(1)
    m = re.search(r"展覽期間計費.*?每增加半小時加收 (\d+) 元", text)
    if m:
        rates["展覽_半小時"] = m.group(1)
    m = re.search(r"隔夜停車費 (\d+) 元", text)
    if m:
        rates["過夜"] = m.group(1)
    return rates


def _parse_date_ranges(text: str, year: int) -> list[tuple[date, date]]:
    """解析 '10/1–10/11、10/13' 這類日期字串。"""
    ranges: list[tuple[date, date]] = []
    for part in text.split("、"):
        nums = re.findall(r"(\d{1,2})/(\d{1,2})", part)
        if nums:
            (sm, sd), (em, ed) = nums[0], nums[-1]
            ranges.append((date(year, int(sm), int(sd)), date(year, int(em), int(ed))))
    return ranges


def find_today_expo_rate(text: str, today: date) -> dict | None:
    """從「指定展期費率」區塊找出今天適用的展期費率，沒有則回傳 None。"""
    block = re.search(r"指定展期費率(.+?)逾 22:00", text)
    if not block:
        return None
    pattern = r"([\d/–\-~、]+) (\d+) 元／小時 (無最高上限|當日當次最高 (\d+) 元)"
    for m in re.finditer(pattern, block.group(1)):
        for start, end in _parse_date_ranges(m.group(1), today.year):
            if start <= today <= end:
                return {"rate": m.group(2), "cap": m.group(4)}
    return None


def is_expo_today(hall: str, events: list[dict]) -> tuple[bool, list[str]]:
    today = datetime.now().date()
    ongoing: list[str] = []
    for e in events:
        if not e["year"] or not e["start"] or not e["end"]:
            continue
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


HALL_LOGOS = {
    "1館": "https://www.tainex.com.tw/assets/img/legacy/tainex1_logo.jpg",
    "2館": "https://www.tainex.com.tw/assets/img/legacy/tainex2_logo.jpg",
}


# ── UI 元件 ──────────────────────────────────────────
def build_parking_card(hall_name: str, parking: dict[str, str], events: list[dict]) -> ft.Card:
    if hall_name not in parking:
        return ft.Card(content=ft.Container(
            ft.Text(f"{hall_name} 資料無法取得"), padding=16,
        ))

    text = parking[hall_name]
    r = extract_rates(text)
    expo_rate = find_today_expo_rate(text, date.today())
    _, expo_names = is_expo_today(hall_name, events)
    overnight = r.get("過夜", "?")

    if expo_rate:
        period = "展覽期間"
        badge_color = ft.Colors.RED_100
        badge_text_color = ft.Colors.RED_700
        price = expo_rate["rate"]
        price_unit = "元/小時"
        half_hr = r.get("展覽_半小時", "?")
        daily_max = f"{expo_rate['cap']}元" if expo_rate["cap"] else "無上限"
        detail = f"超過1小時 每半小時 +{half_hr}元"
        status = f"📌 進行中: {'、'.join(expo_names[:2])}" if expo_names else "📌 今日適用展期費率"
    else:
        period = "非展覽期間"
        badge_color = ft.Colors.GREEN_100
        badge_text_color = ft.Colors.GREEN_700
        price = r.get("一般_每小時", "?")
        price_unit = "元/小時"
        half_hr = r.get("一般_半小時", "?")
        daily_max = r.get("一般_每日上限", "?") + "元"
        detail = f"超過1小時 每半小時 +{half_hr}元"
        status = "📌 目前無展覽"

    return ft.Card(
        content=ft.Container(
            ft.Column([
                ft.Row([
                    ft.Image(src=HALL_LOGOS.get(hall_name, ""), width=40, height=40),
                    ft.Text(hall_name, size=18, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        ft.Text(period, size=12, weight=ft.FontWeight.BOLD, color=badge_text_color),
                        bgcolor=badge_color, border_radius=20, padding=ft.Padding(left=12, top=8, right=12, bottom=8),
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1),
                ft.Row([
                    _rate_tile("目前費率", f"${price}", price_unit, badge_text_color),
                    _rate_tile("每日上限", daily_max, "", ft.Colors.ORANGE_700),
                    _rate_tile("過夜費", f"${overnight}", "元", ft.Colors.GREY_600),
                ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
                ft.Text(detail, size=13, color=ft.Colors.GREY_600),
                ft.Text(status, size=13, color=badge_text_color),
            ], spacing=8),
            padding=16,
        ),
    )


def _rate_tile(label: str, value: str, unit: str, color) -> ft.Column:
    return ft.Column([
        ft.Text(label, size=11, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER),
        ft.Text(value, size=26, weight=ft.FontWeight.BOLD, color=color, text_align=ft.TextAlign.CENTER),
        ft.Text(unit, size=11, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER),
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)


def build_event_list(events: list[dict]) -> ft.Card:
    rows: list[ft.Control] = []
    for i, e in enumerate(events):
        date_str = f"{e['year']} {e['start']}~{e['end']}" if e["start"] else "未定"
        hall = e["hall"] or ""
        loc = e["location"] or ""
        subtitle_parts = [date_str]
        if hall:
            subtitle_parts.append(hall)
        if loc:
            subtitle_parts.append(loc)

        rows.append(ft.ListTile(
            leading=ft.CircleAvatar(
                content=ft.Text(str(i + 1), size=12),
                radius=16,
                bgcolor=ft.Colors.BLUE_100,
                color=ft.Colors.BLUE_700,
            ),
            title=ft.Text(e["name"], size=14, max_lines=2),
            subtitle=ft.Text(" ｜ ".join(subtitle_parts), size=12, color=ft.Colors.GREY_600),
            url=e["url"],
            dense=True,
        ))
        if i < len(events) - 1:
            rows.append(ft.Divider(height=1))

    return ft.Card(
        content=ft.Container(
            ft.Column([
                ft.Text(f"📅 近期展覽（共 {len(events)} 場）", size=18, weight=ft.FontWeight.BOLD),
                ft.Divider(height=1),
                *rows,
            ], spacing=0, scroll=ft.ScrollMode.AUTO),
            padding=16,
        ),
    )


# ── 行事曆 ──────────────────────────────────────────
HALL1_COLOR = ft.Colors.BLUE_200
HALL2_COLOR = ft.Colors.ORANGE_200
BOTH_HALL_COLOR = ft.Colors.PURPLE_200


def _parse_event_dates(events: list[dict]) -> dict[date, set[str]]:
    """回傳 {date: set of hall names} 的對照表。"""
    date_halls: dict[date, set[str]] = {}
    for e in events:
        if not e["year"] or not e["start"] or not e["end"]:
            continue
        try:
            year = int(e["year"])
            s_m, s_d = e["start"].split("/")
            e_m, e_d = e["end"].split("/")
            start = date(year, int(s_m), int(s_d))
            end = date(year, int(e_m), int(e_d))
            d = start
            while d <= end:
                if d not in date_halls:
                    date_halls[d] = set()
                if "1館" in e.get("hall", ""):
                    date_halls[d].add("1館")
                if "2館" in e.get("hall", ""):
                    date_halls[d].add("2館")
                d = date(d.year, d.month, d.day + 1) if d.day < 28 else d.replace(day=1, month=d.month + 1) if d.month < 12 else d.replace(day=1, month=1, year=d.year + 1)
        except (ValueError, TypeError):
            continue
    return date_halls


def _next_day(d: date) -> date:
    from datetime import timedelta
    return d + timedelta(days=1)


def _parse_event_dates_safe(events: list[dict]) -> dict[date, set[str]]:
    """回傳 {date: set of hall names}。"""
    from datetime import timedelta
    date_halls: dict[date, set[str]] = {}
    for e in events:
        if not e["year"] or not e["start"] or not e["end"]:
            continue
        try:
            year = int(e["year"])
            s_m, s_d = e["start"].split("/")
            e_m, e_d = e["end"].split("/")
            start = date(year, int(s_m), int(s_d))
            end = date(year, int(e_m), int(e_d))
            d = start
            while d <= end:
                if d not in date_halls:
                    date_halls[d] = set()
                if "1館" in e.get("hall", ""):
                    date_halls[d].add("1館")
                if "2館" in e.get("hall", ""):
                    date_halls[d].add("2館")
                d += timedelta(days=1)
        except (ValueError, TypeError):
            continue
    return date_halls


def _day_color(halls: set[str]) -> str | None:
    if "1館" in halls and "2館" in halls:
        return BOTH_HALL_COLOR
    if "1館" in halls:
        return HALL1_COLOR
    if "2館" in halls:
        return HALL2_COLOR
    return None


PARKING_DISCOUNT_LIMIT = 10
_discount_file: Path | None = None


def _get_discount_file() -> Path:
    """取得停車優惠資料檔路徑，優先使用環境變數指定的 app data 目錄。"""
    global _discount_file
    if _discount_file is None:
        import os
        # Android 打包後 FLET_APP_STORAGE_DATA 會指向可寫的 app data 目錄
        app_dir = os.environ.get("FLET_APP_STORAGE_DATA")
        if app_dir:
            _discount_file = Path(app_dir) / "parking_discount.json"
        else:
            _discount_file = Path(__file__).parent / "parking_discount.json"
    return _discount_file


def _load_all_discounts() -> dict[str, list[str]]:
    f = _get_discount_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_all_discounts(data: dict[str, list[str]]) -> None:
    f = _get_discount_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_discount_dates(y: int, m: int) -> set[str]:
    key = f"{y}_{m:02d}"
    data = _load_all_discounts()
    return set(data.get(key, []))


def _save_discount_dates(y: int, m: int, dates: set[str]) -> None:
    key = f"{y}_{m:02d}"
    data = _load_all_discounts()
    data[key] = sorted(dates)
    _save_all_discounts(data)


def _build_day_cell(day_num: int, d: date, halls: set[str], is_today: bool, is_discount: bool, on_tap) -> ft.Container:
    """建立單日格子：上方用色條標示館別，下方顯示日期數字。"""
    bars: list[ft.Control] = []
    if "1館" in halls:
        bars.append(ft.Container(height=5, bgcolor=HALL1_COLOR, border_radius=1))
    if "2館" in halls:
        bars.append(ft.Container(height=5, bgcolor=HALL2_COLOR, border_radius=1))

    # 停車優惠標記：日期下方加圓點
    day_text = ft.Text(
        str(day_num), size=12, text_align=ft.TextAlign.CENTER,
        weight=ft.FontWeight.BOLD if is_today else ft.FontWeight.NORMAL,
        color=ft.Colors.WHITE if is_today else ft.Colors.GREY_700,
    )
    discount_dot = ft.Container(
        width=6, height=6, border_radius=3,
        bgcolor=ft.Colors.GREEN_400 if is_discount else None,
    )

    return ft.Container(
        ft.Column([
            ft.Column(bars, spacing=1) if bars else ft.Container(height=5),
            day_text,
            ft.Row([discount_dot], alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        bgcolor=ft.Colors.BLUE_700 if is_today else None,
        border_radius=6, height=42,
        alignment=ft.Alignment(0, 0), expand=True,
        on_click=on_tap,
        ink=True,
    )


def _build_month_grid(y: int, m: int, date_halls: dict, today: date, discount_dates: set[str], on_day_tap) -> ft.Column:
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    header = ft.Row(
        [ft.Container(ft.Text(wd, size=11, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_600), expand=True) for wd in weekdays],
        spacing=2,
    )
    cal = calendar.monthcalendar(y, m)
    day_rows: list[ft.Row] = []
    for week in cal:
        cells: list[ft.Control] = []
        for day_num in week:
            if day_num == 0:
                cells.append(ft.Container(expand=True, height=42))
            else:
                d = date(y, m, day_num)
                halls = date_halls.get(d, set())
                is_today = d == today
                d_str = d.isoformat()
                is_discount = d_str in discount_dates
                cells.append(_build_day_cell(day_num, d, halls, is_today, is_discount, lambda e, ds=d_str: on_day_tap(ds)))
        day_rows.append(ft.Row(cells, spacing=2))
    return ft.Column([header, *day_rows], spacing=4)


def build_calendar(events: list[dict], page: ft.Page) -> ft.Card:
    """建立可切換的雙月行事曆，標記展覽日期與停車優惠使用。"""
    today = date.today()
    date_halls = _parse_event_dates_safe(events)
    current_offset = [0]

    nav_label = ft.Text("", size=15, weight=ft.FontWeight.BOLD)
    month1_title = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
    month2_title = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
    month1_grid = ft.Column()
    month2_grid = ft.Column()
    discount_counter = ft.Text("", size=13, weight=ft.FontWeight.BOLD)

    def _offset_month(base_month, base_year, offset):
        m = base_month + offset
        y = base_year
        while m > 12:
            m -= 12
            y += 1
        while m < 1:
            m += 12
            y -= 1
        return y, m

    def _get_current_month_count():
        """取得當月已用優惠次數。"""
        disc = _load_discount_dates(today.year, today.month)
        return len(disc)

    def _update_counter():
        used = _get_current_month_count()
        remain = PARKING_DISCOUNT_LIMIT - used
        color = ft.Colors.GREEN_700 if remain > 3 else ft.Colors.ORANGE_700 if remain > 0 else ft.Colors.RED_700
        discount_counter.value = f"本月停車優惠：已用 {used}/{PARKING_DISCOUNT_LIMIT} 次，剩餘 {remain} 次"
        discount_counter.color = color

    def on_day_tap(d_str: str):
        """點擊日期切換優惠標記。"""
        d = date.fromisoformat(d_str)
        disc = _load_discount_dates(d.year, d.month)
        if d_str in disc:
            disc.remove(d_str)
        else:
            disc.add(d_str)
        _save_discount_dates(d.year, d.month, disc)
        _update_counter()
        render()

    def render():
        y1, m1 = _offset_month(today.month, today.year, current_offset[0])
        y2, m2 = _offset_month(today.month, today.year, current_offset[0] + 1)

        nav_label.value = f"{y1}/{m1:02d} – {y2}/{m2:02d}"
        month1_title.value = f"{y1} 年 {m1} 月"
        month2_title.value = f"{y2} 年 {m2} 月"

        disc1 = _load_discount_dates(y1, m1)
        disc2 = _load_discount_dates(y2, m2)

        g1 = _build_month_grid(y1, m1, date_halls, today, disc1, on_day_tap)
        month1_grid.controls = g1.controls
        g2 = _build_month_grid(y2, m2, date_halls, today, disc2, on_day_tap)
        month2_grid.controls = g2.controls
        _update_counter()
        page.update()

    def prev_month(e):
        current_offset[0] -= 1
        render()

    def next_month(e):
        current_offset[0] += 1
        render()

    render()

    legend = ft.Row([
        ft.Container(width=20, height=5, bgcolor=HALL1_COLOR, border_radius=1),
        ft.Text("1館", size=11),
        ft.Container(width=20, height=5, bgcolor=HALL2_COLOR, border_radius=1),
        ft.Text("2館", size=11),
        ft.Container(width=6, height=6, bgcolor=ft.Colors.GREEN_400, border_radius=3),
        ft.Text("停車優惠", size=11),
    ], spacing=8)

    nav_row = ft.Row([
        ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=prev_month, icon_size=20),
        nav_label,
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=next_month, icon_size=20),
    ], alignment=ft.MainAxisAlignment.CENTER)

    return ft.Card(
        content=ft.Container(
            ft.Column([
                ft.Text("📆 展覽行事曆", size=18, weight=ft.FontWeight.BOLD),
                ft.Divider(height=1),
                discount_counter,
                ft.Text("點擊日期標記停車優惠使用", size=11, color=ft.Colors.GREY_500),
                legend,
                nav_row,
                month1_title,
                month1_grid,
                ft.Divider(height=1),
                month2_title,
                month2_grid,
            ], spacing=10),
            padding=16,
        ),
    )


# ── 主程式 ──────────────────────────────────────────
def main(page: ft.Page):
    page.title = "南港展覽館"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0

    timestamp = ft.Text("", size=12, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)
    content_col = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    progress = ft.ProgressBar(visible=False)

    def do_refresh(e=None):
        progress.visible = True
        content_col.controls.clear()
        content_col.controls.append(
            ft.Container(
                ft.Text("正在擷取資料...", text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_500),
                alignment=ft.Alignment(0, 0), padding=40,
            )
        )
        page.update()

        def fetch():
            try:
                events = fetch_exhibitions()
                parking = fetch_parking_info()
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                content_col.controls.clear()
                for hall in ["1館", "2館"]:
                    content_col.controls.append(build_parking_card(hall, parking, events))
                content_col.controls.append(build_calendar(events, page))
                content_col.controls.append(build_event_list(events))

                timestamp.value = f"更新時間：{now}"
            except Exception as ex:
                content_col.controls.clear()
                content_col.controls.append(ft.Container(
                    ft.Text(f"❌ 擷取失敗: {ex}", color=ft.Colors.RED_700),
                    padding=20,
                ))
                timestamp.value = "更新失敗"
            finally:
                progress.visible = False
                page.update()

        threading.Thread(target=fetch, daemon=True).start()

    page.appbar = ft.AppBar(
        title=ft.Text("🏛️ 南港展覽館", size=20, weight=ft.FontWeight.BOLD),
        center_title=True,
        bgcolor=ft.Colors.BLUE_700,
        color=ft.Colors.WHITE,
        actions=[
            ft.IconButton(ft.Icons.REFRESH, icon_color=ft.Colors.WHITE, on_click=do_refresh, tooltip="更新"),
        ],
    )

    page.add(
        progress,
        ft.Container(timestamp, padding=ft.Padding(top=8), alignment=ft.Alignment(0, 0)),
        ft.Container(content_col, padding=ft.Padding(left=12, right=12), expand=True),
    )

    do_refresh()


ft.run(main)
