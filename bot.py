import os
import re
import time
import threading
import requests

from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer


TEHRAN = ZoneInfo("Asia/Tehran")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

CONTACT_NUMBER = "09145200578"


MESGHAL_URLS = [
    "https://www.tgju.org/profile/mesghal",
    "https://gem.tgju.org/profile/mesghal",
]

GRAM18_URLS = [
    "https://www.tgju.org/profile/geram18",
    "https://gem.tgju.org/profile/geram18",
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Android 12) "
        "AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36"
    )
}


day_date = None
first_price = None
last_price = None
highest_price = None
lowest_price = None
previous_price = None
report_sent = False


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )
    print(f"Web server listening on port {port}")
    server.serve_forever()


def persian_digits_to_english(text):
    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )
    return text.translate(table)


def clean_number(text):
    text = persian_digits_to_english(text)
    text = text.replace(",", "")
    text = text.replace("٬", "")
    text = text.replace("،", "")

    numbers = re.findall(r"\d+", text)

    if not numbers:
        return None

    return int("".join(numbers))


def get_price(urls):
    for url in urls:
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=10
            )

            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            text = soup.get_text(
                " ",
                strip=True
            )

            match = re.search(
                r"نرخ فعلی\s*[:：]?\s*([\d,٬،۰-۹٠-٩]+)",
                text
            )

            if match:
                rial_price = clean_number(
                    match.group(1)
                )

                if rial_price:
                    return rial_price // 10

        except Exception as e:
            print(
                "خطا در دریافت قیمت:",
                url,
                e
            )

    return None


def get_prices():
    mesghal = get_price(MESGHAL_URLS)
    gram18 = get_price(GRAM18_URLS)

    return mesghal, gram18


def gregorian_to_jalali(gy, gm, gd):
    g_days_in_month = [
        31, 28, 31, 30, 31, 30,
        31, 31, 30, 31, 30, 31
    ]

    jy = 979

    gy2 = gy - 1600

    days = (
        365 * gy2
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
    )

    for i in range(gm - 1):
        days += g_days_in_month[i]

    if gm > 2:
        if (
            (gy % 4 == 0 and gy % 100 != 0)
            or gy % 400 == 0
        ):
            days += 1

    jy += 33 * (days // 12053)
    days %= 12053

    jy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30

    return jy, jm, jd


def jalali_date():
    now = datetime.now(TEHRAN)

    jy, jm, jd = gregorian_to_jalali(
        now.year,
        now.month,
        now.day
    )

    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def format_price(price):
    return f"{price:,}"


def send_telegram(message):
    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(
            url,
            data=data,
            timeout=15
        )

        if not response.ok:
            print(
                "خطای تلگرام:",
                response.text
            )

        return response.ok

    except Exception as e:
        print(
            "خطا در ارسال به تلگرام:",
            e
        )

        return False


def send_live_message(
    mesghal,
    gram18,
    change,
    now
):
    message = f"""🟡 <b>قیمت لحظه‌ای طلای آبشده رسولی‌زاده</b>

⚖️ مثقال طلا: <b>{format_price(mesghal)} تومان</b>
💰 هر گرم طلا: <b>{format_price(gram18)} تومان</b>
📈 تغییر قیمت: <b>{change:+,} تومان</b>

📅 تاریخ: <b>{jalali_date()}</b>
🕐 ساعت بروزرسانی: <b>{now.strftime("%H:%M:%S")}</b>

📞 <b>تماس: {CONTACT_NUMBER}</b>"""

    send_telegram(message)


def send_daily_report():
    global report_sent

    if first_price is None or last_price is None:
        print(
            "اطلاعات کافی برای گزارش امروز وجود ندارد."
        )

        report_sent = True
        return

    message = f"""📊 <b>گزارش معاملات طلای آبشده رسولی‌زاده</b>

📅 تاریخ: <b>{jalali_date()}</b>

🔵 اولین معامله: <b>{format_price(first_price)} تومان</b>

🔺 سقف معاملات: <b>{format_price(highest_price)} تومان</b>

🔻 کف معاملات: <b>{format_price(lowest_price)} تومان</b>

🟢 آخرین معامله: <b>{format_price(last_price)} تومان</b>

با تشکر"""

    if send_telegram(message):
        report_sent = True
        print(
            "گزارش ساعت 21 ارسال شد."
        )


def reset_day_if_needed(now):
    global day_date
    global first_price
    global last_price
    global highest_price
    global lowest_price
    global previous_price
    global report_sent

    today = now.date()

    if day_date != today and now.hour >= 9:
        day_date = today

        first_price = None
        last_price = None
        highest_price = None
        lowest_price = None
        previous_price = None
        report_sent = False

        print("روز جدید شروع شد.")


def process_prices():
    global first_price
    global last_price
    global highest_price
    global lowest_price
    global previous_price

    mesghal, gram18 = get_prices()

    if mesghal is None or gram18 is None:
        print("قیمت دریافت نشد.")
        return

    if (
        highest_price is None
        or mesghal > highest_price
    ):
        highest_price = mesghal

    if (
        lowest_price is None
        or mesghal < lowest_price
    ):
        lowest_price = mesghal

    if first_price is None:
        first_price = mesghal
        last_price = mesghal
        previous_price = mesghal

        now = datetime.now(TEHRAN)

        send_live_message(
            mesghal,
            gram18,
            0,
            now
        )

        print(
            "اولین قیمت روز ارسال شد."
        )

        return

    last_price = mesghal

    if mesghal != previous_price:
        change = mesghal - previous_price

        now = datetime.now(TEHRAN)

        send_live_message(
            mesghal,
            gram18,
            change,
            now
        )

        previous_price = mesghal

        print(
            "قیمت تغییر کرد:",
            mesghal
        )


def main():
    threading.Thread(
        target=start_web_server,
        daemon=True
    ).start()

    if not BOT_TOKEN:
        print(
            "BOT_TOKEN تنظیم نشده است."
        )
        return

    if not CHANNEL_ID:
        print(
            "CHANNEL_ID تنظیم نشده است."
        )
        return

    print("ربات شروع شد.")

    while True:
        try:
            now = datetime.now(TEHRAN)

            reset_day_if_needed(now)

            if (
                now.hour >= 21
                and day_date == now.date()
                and not report_sent
            ):
                send_daily_report()

            if 9 <= now.hour < 21:
                process_prices()

            time.sleep(15)

        except Exception as e:
            print(
                "خطای اصلی:",
                e
            )

            time.sleep(15)


if __name__ == "__main__":
    main()
