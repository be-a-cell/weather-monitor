import glob
import os
from pathlib import Path
import matplotlib as mpl
import matplotlib.dates as mdates
from matplotlib import font_manager
import matplotlib.pyplot as plt
import pandas as pd
import requests

# ==========================================
# 0. 路徑與基礎設定 (適應 src/ 結構)
# ==========================================
# 取得專案根目錄 (weather-monitor/)
BASE_DIR = Path(__file__).resolve().parent.parent

# 定義各資料夾與檔案之根目錄路徑
CONFIG_DIR = BASE_DIR / "config"
STATION_DIR = BASE_DIR / "stations_data"
HISTORICAL_DIR = BASE_DIR / "historical_data"

# 建立所需目錄
STATION_DIR.mkdir(parents=True, exist_ok=True)
HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)

# 載入自訂中文字型檔 (包含安全降級機制)
FONT_PATH = CONFIG_DIR / "NotoSansCJKtc-Regular.otf"
font_loaded = False

if FONT_PATH.exists():
    try:
        font_manager.fontManager.addfont(str(FONT_PATH))
        font_prop = font_manager.FontProperties(fname=str(FONT_PATH))
        mpl.rcParams["font.family"] = font_prop.get_name()
        font_loaded = True
        print(f"成功載入本地字型: {FONT_PATH}")
    except Exception as e:
        print(f"本地字型載入失敗 ({e})，自動切換至系統預設中文字型。")

# 若本地字型不存在或載入失敗，則改用系統內建中文字型
if not font_loaded:
    mpl.rcParams["font.sans-serif"] = [
        "Noto Sans CJK TC",
        "Noto Sans TC",
        "WenQuanYi Micro Hei",
        "DejaVu Sans",
    ]

mpl.rcParams["axes.unicode_minus"] = False  # 解決負號顯示異常問題

# ==========================================
# 時間軸自主調整 (格式: "2026-08-01" 或 None)
# ==========================================
START_DATE = None
END_DATE = None

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

# 匯出缺失/異常資料至根目錄獨立 CSV
if invalid_records:
    invalid_df = pd.DataFrame(invalid_records)
    invalid_csv_path = BASE_DIR / "missing_or_invalid_data.csv"
    if invalid_csv_path.exists() and invalid_csv_path.stat().st_size > 0:
        try:
            exist_invalid_df = pd.read_csv(invalid_csv_path)
            invalid_df = pd.concat(
                [exist_invalid_df, invalid_df], ignore_index=True
            ).drop_duplicates()
        except Exception:
            pass
    invalid_df.to_csv(invalid_csv_path, index=False, encoding="utf-8-sig")

# ==========================================
# 2. 獨立測站數據更新與寫入 (整合 historical_data)
# ==========================================
for s_id in target_stations:
    station_incoming = new_df[new_df["StationId"] == s_id].copy()

    # 1. 嘗試讀取 historical_data/ 下的手動歷史檔案 (包含空檔檢查)
    history_matches = list(HISTORICAL_DIR.glob(f"{s_id}_*.csv"))
    historical_df = pd.DataFrame()
    if history_matches:
        hist_file = history_matches[0]
        if hist_file.stat().st_size > 0:
            try:
                historical_df = pd.read_csv(hist_file)
            except pd.errors.EmptyDataError:
                print(f"警告: 歷史檔案 {hist_file.name} 為空白檔案，已跳過。")
            except Exception as e:
                print(f"讀取歷史檔案 {hist_file.name} 失敗: {e}")

    # 2. 嘗試讀取 stations_data/ 下既有的累積檔案 (包含空檔檢查)
    station_matches = list(STATION_DIR.glob(f"{s_id}_*.csv"))
    exist_df = pd.DataFrame()
    if station_matches:
        exist_file = station_matches[0]
        if exist_file.stat().st_size > 0:
            try:
                exist_df = pd.read_csv(exist_file)
            except pd.errors.EmptyDataError:
                print(f"警告: 既有檔案 {exist_file.name} 為空白檔案，已跳過。")
            except Exception as e:
                print(f"讀取既有檔案 {exist_file.name} 失敗: {e}")

    # 3. 合併 historical + existing + newly_fetched
    combined_station_df = pd.concat(
        [historical_df, exist_df, station_incoming], ignore_index=True
    )

    if combined_station_df.empty:
        continue

    # 取得真正的測站名稱
    s_name = combined_station_df["StationName"].dropna().iloc[0]
    station_csv_path = STATION_DIR / f"{s_id}_{s_name}.csv"

    combined_station_df.drop_duplicates(
        subset=["DateTime", "StationId"], inplace=True
    )
    combined_station_df.sort_values(by="DateTime", inplace=True)
    combined_station_df.to_csv(
        station_csv_path, index=False, encoding="utf-8-sig"
    )

# ==========================================
# 3. 彙整歷史總表 weather_history.csv (存放在根目錄)
# ==========================================
all_station_files = list(STATION_DIR.glob("*.csv"))
master_list = []
for f in all_station_files:
    if f.stat().st_size > 0:
        try:
            master_list.append(pd.read_csv(f))
        except Exception:
            pass

master_df = pd.DataFrame()
if master_list:
    master_df = pd.concat(master_list, ignore_index=True)
    master_df.drop_duplicates(subset=["DateTime", "StationId"], inplace=True)
    master_df.sort_values(by=["DateTime", "StationId"], inplace=True)
    master_df.to_csv(
        BASE_DIR / "weather_history.csv", index=False, encoding="utf-8-sig"
    )

# ==========================================
# 4. 繪製圖表 (輸出至根目錄 weather_chart.png)
# ==========================================
if master_list and not master_df.empty:
    plot_df = master_df.copy()

    plot_df["DateTime"] = pd.to_datetime(plot_df["DateTime"])
    plot_df["Temperature"] = pd.to_numeric(
        plot_df["Temperature"], errors="coerce"
    )
    plot_df["Rainfall"] = pd.to_numeric(plot_df["Rainfall"], errors="coerce")

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

        # 【上圖】氣溫折線圖
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

        # 【下圖】雨量直條圖
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

        # X 軸時間軸格式設定
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=45)

        plt.tight_layout()

        chart_filename = BASE_DIR / "weather_chart.png"
        plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"圖表已成功生成: {chart_filename}")
