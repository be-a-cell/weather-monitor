import glob
import os
import shutil
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import requests

# ==========================================
# 0. 中文字型與全域設定 (徹底解決 Linux/GitHub Actions 豆腐塊)
# ==========================================
# 清除 Matplotlib 快取，確保能載入 Ubuntu 系統剛安裝的中文字型
try:
    shutil.rmtree(mpl.get_cachedir())
except Exception:
    pass

# 設定優先使用的繁體中文字型名稱
mpl.rcParams["font.sans-serif"] = [
    "Noto Sans CJK TC",
    "Noto Sans CJK JP",
    "Noto Sans TC",
    "WenQuanYi Micro Hei",
    "DejaVu Sans",
]
mpl.rcParams["axes.unicode_minus"] = False  # 解決負號變方塊問題

# ==========================================
# 時間軸自主調整 (格式: "2026-08-01" 或 None)
# ==========================================
START_DATE = None
END_DATE = None

STATION_DIR = "stations_data"
os.makedirs(STATION_DIR, exist_ok=True)

# ==========================================
# 1. 抓取氣象署 API 資料
# ==========================================
API_KEY = os.getenv("CWA_API_KEY")
url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={API_KEY}"

target_stations = ["C0TA40", "C0TA50", "C0Z310", "C0T9D0", "C0Z220", "C0Z230"]
new_records = []
invalid_records = []

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

            # 記錄異常數據
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

# 匯出缺失/異常資料至獨立 CSV
if invalid_records:
    invalid_df = pd.DataFrame(invalid_records)
    invalid_csv_path = "missing_or_invalid_data.csv"
    if os.path.exists(invalid_csv_path):
        exist_invalid_df = pd.read_csv(invalid_csv_path)
        invalid_df = pd.concat(
            [exist_invalid_df, invalid_df], ignore_index=True
        ).drop_duplicates()
    invalid_df.to_csv(invalid_csv_path, index=False, encoding="utf-8-sig")

# ==========================================
# 2. 獨立測站數據更新與寫入
# ==========================================
for s_id in target_stations:
    station_incoming = new_df[new_df["StationId"] == s_id].copy()
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

# ==========================================
# 3. 彙整歷史總表 weather_history.csv
# ==========================================
all_station_files = glob.glob(os.path.join(STATION_DIR, "*.csv"))
master_list = [pd.read_csv(f) for f in all_station_files]

if master_list:
    master_df = pd.concat(master_list, ignore_index=True)
    master_df.drop_duplicates(subset=["DateTime", "StationId"], inplace=True)
    master_df.sort_values(by=["DateTime", "StationId"], inplace=True)
    master_df.to_csv("weather_history.csv", index=False, encoding="utf-8-sig")

# ==========================================
# 4. 繪製圖表 (精確對應欄位與繁體中文顯示)
# ==========================================
if master_list and not master_df.empty:
    plot_df = master_df.copy()

    plot_df["DateTime"] = pd.to_datetime(plot_df["DateTime"])
    plot_df["Temperature"] = pd.to_numeric(
        plot_df["Temperature"], errors="coerce"
    )
    plot_df["Rainfall"] = pd.to_numeric(plot_df["Rainfall"], errors="coerce")

    # 組合 StationId 與 StationName 作為圖例標籤 (例如 "C0TA40 測站名稱")
    plot_df["StationLabel"] = (
        plot_df["StationId"] + " " + plot_df["StationName"]
    )

    # 時間選擇性過濾
    if START_DATE:
        plot_df = plot_df[plot_df["DateTime"] >= pd.to_datetime(START_DATE)]
    if END_DATE:
        plot_df = plot_df[plot_df["DateTime"] <= pd.to_datetime(END_DATE)]

    plot_df.sort_values(by="DateTime", inplace=True)

    if not plot_df.empty:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

        station_labels = plot_df["StationLabel"].unique()
        num_stations = len(station_labels)

        # 【上圖】氣溫折線圖 (X軸: DateTime, Y軸: Temperature, 圖例: StationId StationName)
        for label in station_labels:
            group = plot_df[plot_df["StationLabel"] == label].dropna(
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
                label=label,
            )

        ax1.set_title("即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold")
        ax1.set_ylabel("氣溫 (°C)", fontsize=12)
        ax1.grid(True, linestyle="--", alpha=0.5)
        ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

        # 【下圖】雨量直條圖 (X軸: DateTime, Y軸: Rainfall, 圖例: StationId StationName)
        single_bar_width = 0.012 / max(num_stations, 1)

        for i, label in enumerate(station_labels):
            group = plot_df[plot_df["StationLabel"] == label].dropna(
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
                label=label,
            )

        ax2.set_title("即時雨量直條圖 (mm)", fontsize=14, fontweight="bold")
        ax2.set_xlabel("時間 (DateTime)", fontsize=12)
        ax2.set_ylabel("雨量 (mm)", fontsize=12)
        ax2.grid(True, linestyle="--", alpha=0.5)
        ax2.legend(loc="upper left", bbox_to_anchor=(1, 1))

        # X軸時間軸格式設定
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=45)

        plt.tight_layout()

        chart_filename = "weather_chart.png"
        plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"圖表已成功生成: {chart_filename}")
