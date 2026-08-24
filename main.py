import glob
import os
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties
import matplotlib.pyplot as plt
import pandas as pd
import requests

# ==========================================
# 0. 中文字型設定 (下載並指定字型檔案，徹底解決方框豆腐塊問題)
# ==========================================
font_path = "NotoSansCJKtc-Regular.otf"
# 若本地沒有字型檔，則自動下載思源黑體
if not os.path.exists(font_path):
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    try:
        r = requests.get(font_url, timeout=15)
        with open(font_path, "wb") as f:
            f.write(r.content)
        print("已成功下載中文字型檔：NotoSansCJKtc-Regular.otf")
    except Exception as e:
        print(f"下載字型失敗: {e}")

# 建立字型物件
if os.path.exists(font_path):
    my_font = FontProperties(fname=font_path)
    title_font = FontProperties(fname=font_path, size=14, weight="bold")
else:
    my_font = None
    title_font = None

plt.rcParams["axes.unicode_minus"] = False  # 解決負號無法正常顯示

# ==========================================
# 時間軸自主調整 (設定抓取/繪圖的時間區間)
# 可設定格式: "2026-08-01", "2026-08" 或 None (不限制)
# ==========================================
START_DATE = None  # 例如 "2026-08-01"
END_DATE = None  # 例如 "2026-08-31"

STATION_DIR = "stations_data"
os.makedirs(STATION_DIR, exist_ok=True)

# 1. 抓取氣象署最新資料
API_KEY = os.getenv("CWA_API_KEY")
url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={API_KEY}"

target_stations = ["C0TA40", "C0TA50", "C0Z310", "C0T9D0", "C0Z220", "C0Z230"]
new_records = []
invalid_records = []  # 紀錄沒有成功抓到的資料/異常資料

try:
    response = requests.get(url, timeout=10)
    data = response.json()
except Exception as e:
    print(f"API 請求失敗: {e}")
    data = {}

if "records" in data and "Station" in data["records"]:
    for station in data["records"]["Station"]:
        s_id = station.get("StationId")
        if s_id in target_stations:
            s_name = station.get("StationName", "未知測站")
            obs_time = station.get("ObsTime", {}).get("DateTime", "")

            weather_elem = station.get("WeatherElement", {})

            # 氣溫讀取與檢查
            raw_temp = weather_elem.get("AirTemperature")
            temp_is_invalid = raw_temp in [
                None,
                -99,
                -998,
                "-99",
                "-998",
                "None",
            ]
            temp = float(raw_temp) if not temp_is_invalid else None

            # 雨量讀取與檢查
            raw_rain = weather_elem.get("Now", {}).get("Precipitation")
            rain_is_invalid = raw_rain in [
                None,
                -99,
                -998,
                "-99",
                "-998",
                "None",
            ]
            rain = float(raw_rain) if not rain_is_invalid else None

            # 判斷是否屬於「沒有成功抓到的資料」（排除雨量=0的情況）
            if temp_is_invalid or rain_is_invalid:
                invalid_records.append(
                    {
                        "DateTime": obs_time,
                        "StationId": s_id,
                        "StationName": s_name,
                        "RawTemperature": raw_temp,
                        "RawRainfall": raw_rain,
                        "Issue": (
                            "氣溫異常"
                            if temp_is_invalid and not rain_is_invalid
                            else (
                                "雨量異常"
                                if rain_is_invalid and not temp_is_invalid
                                else "氣溫與雨量皆異常"
                            )
                        ),
                    }
                )

            new_records.append(
                {
                    "DateTime": obs_time,
                    "StationId": s_id,
                    "StationName": s_name,
                    "Temperature": temp,
                    "Rainfall": rain if rain is not None else 0.0,
                }
            )

new_df = pd.DataFrame(new_records)

# 匯出異常紀錄 CSV
if invalid_records:
    invalid_df = pd.DataFrame(invalid_records)
    invalid_csv_path = "missing_or_invalid_data.csv"

    if os.path.exists(invalid_csv_path):
        exist_invalid_df = pd.read_csv(invalid_csv_path)
        invalid_df = pd.concat(
            [exist_invalid_df, invalid_df], ignore_index=True
        ).drop_duplicates()

    invalid_df.to_csv(invalid_csv_path, index=False, encoding="utf-8-sig")
    print(f"已整理無效/缺失數據至: {invalid_csv_path} (共 {len(invalid_df)} 筆)")

# 2. 歷史 CSV 合併
old_records_df = pd.DataFrame()
historical_files = [
    f
    for f in glob.glob("*.csv")
    if f
    not in [
        "weather_history.csv",
        "missing_or_invalid_data.csv",
    ]
    and not f.startswith("stations_data")
]

for old_file in historical_files:
    try:
        temp_df = pd.read_csv(old_file)
        if "StationId" in temp_df.columns and "DateTime" in temp_df.columns:
            temp_df = temp_df[temp_df["StationId"].isin(target_stations)]
            old_records_df = pd.concat(
                [old_records_df, temp_df], ignore_index=True
            )
    except Exception as e:
        print(f"讀取 {old_file} 失敗: {e}")

all_incoming_df = pd.concat([old_records_df, new_df], ignore_index=True)

# 3. 按測站寫入獨立 CSV
for s_id in target_stations:
    station_incoming = all_incoming_df[
        all_incoming_df["StationId"] == s_id
    ].copy()
    if station_incoming.empty:
        continue

    s_name = station_incoming["StationName"].iloc[0]
    station_csv_path = os.path.join(STATION_DIR, f"{s_id}_{s_name}.csv")

    if os.path.exists(station_csv_path):
        exist_df = pd.read_csv(station_csv_path)
        combined_station_df = pd.concat(
            [exist_df, station_incoming], ignore_index=True
        )
    else:
        combined_station_df = station_incoming

    combined_station_df.drop_duplicates(
        subset=["DateTime", "StationId"], inplace=True
    )
    combined_station_df.sort_values(by="DateTime", inplace=True)
    combined_station_df.to_csv(
        station_csv_path, index=False, encoding="utf-8-sig"
    )

# 4. 彙整總表 weather_history.csv
all_station_files = glob.glob(os.path.join(STATION_DIR, "*.csv"))
master_list = []

for s_file in all_station_files:
    m_df = pd.read_csv(s_file)
    master_list.append(m_df)

if master_list:
    master_df = pd.concat(master_list, ignore_index=True)
    master_df.drop_duplicates(subset=["DateTime", "StationId"], inplace=True)
    master_df.sort_values(by=["DateTime", "StationId"], inplace=True)

    master_filename = "weather_history.csv"
    master_df.to_csv(master_filename, index=False, encoding="utf-8-sig")

# ==========================================
# 5. 繪製圖表 (精確傳入 fontproperties 確保繁體中文正確顯示)
# ==========================================
if master_list and not master_df.empty:
    plot_df = master_df.copy()

    plot_df["DateTime"] = pd.to_datetime(plot_df["DateTime"])
    plot_df["Temperature"] = pd.to_numeric(
        plot_df["Temperature"], errors="coerce"
    )
    plot_df["Rainfall"] = pd.to_numeric(plot_df["Rainfall"], errors="coerce")

    # --- 時間軸自主過濾 ---
    if START_DATE:
        plot_df = plot_df[plot_df["DateTime"] >= pd.to_datetime(START_DATE)]
    if END_DATE:
        end_dt = pd.to_datetime(END_DATE)
        if len(END_DATE) <= 7:
            end_dt = end_dt + pd.offsets.MonthEnd(1) + pd.Timedelta(days=1)
        plot_df = plot_df[plot_df["DateTime"] <= end_dt]

    plot_df.sort_values(by="DateTime", inplace=True)

    if not plot_df.empty:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

        station_names = plot_df["StationName"].unique()
        num_stations = len(station_names)

        # 1. 氣溫折線圖
        for station_name in station_names:
            group = plot_df[plot_df["StationName"] == station_name].dropna(
                subset=["Temperature"]
            )
            if group.empty:
                continue
            ax1.plot(
                group["DateTime"],
                group["Temperature"],
                marker="o",
                markersize=3,
                linewidth=1.5,
                label=station_name,
            )

        ax1.set_title("即時氣溫變化圖 (°C)", fontproperties=title_font)
        ax1.set_ylabel("氣溫 (°C)", fontproperties=my_font)
        ax1.grid(True, linestyle="--", alpha=0.5)
        ax1.legend(
            loc="upper left", bbox_to_anchor=(1, 1), prop=my_font
        )  # 注意：圖例使用 prop

        # 2. 雨量直條圖
        single_bar_width = 0.012 / max(num_stations, 1)

        for i, station_name in enumerate(station_names):
            group = plot_df[plot_df["StationName"] == station_name].dropna(
                subset=["Rainfall"]
            )
            if group.empty:
                continue

            offset = (i - (num_stations - 1) / 2) * single_bar_width
            x_dates = mdates.date2num(group["DateTime"]) + offset

            ax2.bar(
                x_dates,
                group["Rainfall"],
                width=single_bar_width,
                alpha=0.7,
                label=station_name,
            )

        ax2.set_title("即時雨量直條圖 (mm)", fontproperties=title_font)
        ax2.set_xlabel("時間", fontproperties=my_font)
        ax2.set_ylabel("雨量 (mm)", fontproperties=my_font)
        ax2.grid(True, linestyle="--", alpha=0.5)
        ax2.legend(loc="upper left", bbox_to_anchor=(1, 1), prop=my_font)

        # 設定 X 軸時間顯示格式
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=45)

        plt.tight_layout()

        chart_filename = "weather_chart.png"
        plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"圖表繪製完成: {chart_filename}")
