from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3
import sys
import time
import matplotlib as mpl
import matplotlib.dates as mdates
from matplotlib import font_manager
import matplotlib.pyplot as plt
import pandas as pd
from playwright.sync_api import sync_playwright

# ==========================================
# 0. 路徑與基礎設定
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
STATIONS_DIR = BASE_DIR / "stations_data"
DB_PATH = BASE_DIR / "src" / "weather_database.db"
CHART_PATH = BASE_DIR / "weather_chart.png"

STATIONS_DIR.mkdir(parents=True, exist_ok=True)

STATIONS = ["C0T9D0", "C0TA40", "C0TA50", "C0Z220", "C0Z230", "C0Z310"]

# 💡 依圖片更正的測站名稱對照
STATION_NAMES = {
    "C0T9D0": "和平",
    "C0TA40": "秀林",
    "C0TA50": "和仁",
    "C0Z220": "和平林道",
    "C0Z230": "和平",
    "C0Z310": "清水斷崖",
}

STATION_COLORS = {
    "C0T9D0": "#5B9BD5",  # 和平 (藍)
    "C0TA40": "#FF5809",  # 秀林 (橘紅)
    "C0TA50": "#A23400",  # 和仁 (棕紅)
    "C0Z220": "#70AD47",  # 和平林道 (綠)
    "C0Z230": "#3399FF",  # 和平 (亮藍)
    "C0Z310": "#1F4E79",  # 清水斷崖 (深藍)
}

START_DATE = datetime(2022, 1, 1)
END_DATE = datetime.now()

# 中文字型設定
FONT_PATH = CONFIG_DIR / "NotoSansCJKtc-Regular.otf"
chosen_font_prop = None
if FONT_PATH.exists():
    try:
        font_manager.fontManager.addfont(str(FONT_PATH))
        chosen_font_prop = font_manager.FontProperties(fname=str(FONT_PATH))
        mpl.rcParams["font.family"] = chosen_font_prop.get_name()
    except Exception:
        pass

if chosen_font_prop is None:
    mpl.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "DejaVu Sans"]
    chosen_font_prop = font_manager.FontProperties(
        family=["Noto Sans CJK TC", "DejaVu Sans"]
    )

mpl.rcParams["axes.unicode_minus"] = False


# ==========================================
# 1. SQLite 資料庫操作
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_records (
            station_id TEXT,
            station_name TEXT,
            datetime TEXT,
            temperature REAL,
            rainfall REAL,
            PRIMARY KEY (station_id, datetime)
        )
    """)
    conn.commit()
    conn.close()


def save_to_db(records):
    if not records:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT OR REPLACE INTO weather_records (station_id, station_name, datetime, temperature, rainfall)
        VALUES (:station_id, :station_name, :obs_time, :temperature, :rainfall)
    """,
        records,
    )
    conn.commit()
    conn.close()


def get_db_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM weather_records", conn)
    conn.close()
    if not df.empty:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
        df["rainfall"] = pd.to_numeric(df["rainfall"], errors="coerce")
        df = df.dropna(subset=["datetime"]).sort_values(by="datetime")
    return df


# ==========================================
# 2. CODIS 數據爬取
# ==========================================
def get_stn_type(stn_id):
    return "auto" if stn_id in ["C0TA40", "C0TA50"] else "auto_C0"


def fetch_weather_data():
    init_db()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        print("🌐 初始化 CODIS Session...")
        page.goto("https://codis.cwa.gov.tw/StationData")
        page.wait_for_timeout(3000)

        total_days = (END_DATE - START_DATE).days + 1
        for i in range(total_days):
            current_date = START_DATE + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")

            daily_records = []
            for stn_id in STATIONS:
                stn_type = get_stn_type(stn_id)
                stn_name = STATION_NAMES.get(stn_id, stn_id)

                fetch_script = f"""
                async () => {{
                    const formData = new URLSearchParams();
                    formData.append('date', '{date_str}T00:00:00+08:00');
                    formData.append('type', 'report_date');
                    formData.append('stn_ID', '{stn_id}');
                    formData.append('stn_type', '{stn_type}');
                    formData.append('more', '');
                    formData.append('start', '{date_str}T00:00:00');
                    formData.append('end', '{date_str}T23:59:59');
                    formData.append('item', '');

                    const response = await fetch('https://codis.cwa.gov.tw/api/station?', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest'
                        }},
                        body: formData
                    }});
                    return await response.json();
                }}
                """
                try:
                    res_data = page.evaluate(fetch_script)
                    station_list = (
                        res_data.get("data", [])
                        if isinstance(res_data, dict)
                        else []
                    )
                    if station_list and isinstance(station_list, list):
                        dts_list = station_list[0].get("dts", [])
                        for row in dts_list:
                            obs_time = row.get("DataTime") or row.get("ObsTime")
                            temp_obj = row.get("AirTemperature", {})
                            temp = (
                                temp_obj.get("Instantaneous")
                                if isinstance(temp_obj, dict)
                                else temp_obj
                            )
                            rain_obj = row.get("Precipitation", {})
                            rain = (
                                rain_obj.get("Accumulation")
                                if isinstance(rain_obj, dict)
                                else rain_obj
                            )

                            if obs_time:
                                daily_records.append({
                                    "station_id": stn_id,
                                    "station_name": stn_name,
                                    "obs_time": obs_time.replace("T", " "),
                                    "temperature": temp,
                                    "rainfall": rain,
                                })
                except Exception as e:
                    print(f"⚠️ {date_str} {stn_id} 抓取異常: {e}")

            if daily_records:
                save_to_db(daily_records)
                print(
                    f"✅ {date_str} 成功存入 {len(daily_records)} 筆數據至 SQLite"
                )

        browser.close()


# ==========================================
# 3. 匯出個別測站 CSV 與繪圖
# ==========================================
def export_individual_csvs(master_df):
    """將資料庫內的總數據拆分匯出成獨立的測站 CSV"""
    if master_df.empty:
        return

    for stn_id, stn_name in STATION_NAMES.items():
        stn_df = master_df[master_df["station_id"] == stn_id].copy()
        if not stn_df.empty:
            csv_path = STATIONS_DIR / f"{stn_id}_{stn_name}.csv"
            export_df = stn_df.copy()
            export_df["datetime"] = export_df["datetime"].dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            export_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"📁 已匯出個站檔案：{csv_path.name}")


def generate_chart():
    master_df = get_db_data()
    if master_df.empty:
        print("❌ 無數據可繪製圖表。")
        return

    # 匯出各站獨立 CSV
    export_individual_csvs(master_df)

    plot_df = master_df.copy()
    plot_df["StationLabel"] = (
        plot_df["station_id"] + " " + plot_df["station_name"]
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    station_labels = plot_df["StationLabel"].unique()

    total_days = (
        plot_df["datetime"].max() - plot_df["datetime"].min()
    ).total_seconds() / 86400
    dynamic_bar_width = max(total_days * 0.003, 0.5)

    # 1. 氣溫折線圖
    for label in station_labels:
        s_id = label.split()[0]
        group = plot_df[plot_df["StationLabel"] == label].dropna(
            subset=["temperature"]
        )
        if group.empty:
            continue
        ax1.plot(
            group["datetime"],
            group["temperature"],
            marker="o",
            markersize=1.5,
            linewidth=1,
            label=label,
            color=STATION_COLORS.get(s_id, "#333333"),
        )

    t_title = ax1.set_title(
        "即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold"
    )
    t_ylabel = ax1.set_ylabel("氣溫 (°C)", fontsize=12)
    ax1.grid(True, linestyle="--", alpha=0.5)
    leg1 = ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # 2. 雨量直條圖
    for label in station_labels:
        s_id = label.split()[0]
        group = plot_df[plot_df["StationLabel"] == label].dropna(
            subset=["rainfall"]
        )
        if group.empty:
            continue
        rain_positive = group[group["rainfall"] > 0]

        if not rain_positive.empty:
            ax2.bar(
                rain_positive["datetime"],
                rain_positive["rainfall"],
                width=dynamic_bar_width,
                alpha=0.6,
                label=label,
                color=STATION_COLORS.get(s_id, "#333333"),
            )
        else:
            ax2.plot(
                group["datetime"].iloc[:1],
                group["rainfall"].iloc[:1],
                alpha=0,
                label=label,
                color=STATION_COLORS.get(s_id, "#333333"),
            )

    r_title = ax2.set_title(
        "即時雨量直條圖 (mm)", fontsize=14, fontweight="bold"
    )
    r_xlabel = ax2.set_xlabel("時間 (DateTime)", fontsize=12)
    r_ylabel = ax2.set_ylabel("雨量 (mm)", fontsize=12)
    ax2.grid(True, linestyle="--", alpha=0.5)
    leg2 = ax2.legend(loc="upper left", bbox_to_anchor=(1, 1))

    max_rain = plot_df["rainfall"].max()
    ax2.set_ylim(0, max_rain * 1.1 if pd.notna(max_rain) and max_rain > 0 else 10)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=45)

    if chosen_font_prop:
        t_title.set_fontproperties(chosen_font_prop)
        t_ylabel.set_fontproperties(chosen_font_prop)
        r_title.set_fontproperties(chosen_font_prop)
        r_xlabel.set_fontproperties(chosen_font_prop)
        r_ylabel.set_fontproperties(chosen_font_prop)
        for text in leg1.get_texts() + leg2.get_texts():
            text.set_fontproperties(chosen_font_prop)
        for ax in [ax1, ax2]:
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontproperties(chosen_font_prop)

    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"📊 圖表已成功生成: {CHART_PATH}")


if __name__ == "__main__":
    fetch_weather_data()
    generate_chart()
