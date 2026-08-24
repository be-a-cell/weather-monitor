import glob
import os
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
import requests

# ==========================================
# 0. 中文字型與繪圖設定 (解決圖片字顯示不出來的問題)
# ==========================================
# 嘗試自動下載與載入思源黑體（若系統無中文字型時）
try:
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
    font_path = "NotoSansCJKtc-Regular.otf"
    if not os.path.exists(font_path):
        r = requests.get(font_url, timeout=10)
        with open(font_path, "wb") as f:
            f.write(r.content)
    fm.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = fm.FontProperties(
        fname=font_path
    ).get_name()
except Exception as e:
    # 備用：系統常見繁體中文字型
    plt.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei",
        "Arial Unicode MS",
        "MingLiU",
        "WenQuanYi Zen Hei",
        "DejaVu Sans",
    ]

plt.rcParams["axes.unicode_minus"] = False  # 解決負號變方框問題

# ==========================================
# 時間軸範圍設定 (自主調整年月日或年月)
# 例如: "2026-08-01" 至 "2026-08-31"，或留空 None 顯示全部
# ==========================================
START_DATE = None  # 例如 "2026-08-01" 或 "2026-08"
END_DATE = None  # 例如 "2026-08-25" 或 "2026-08"

# 建立放置各測站獨立 CSV 的資料夾
STATION_DIR = "stations_data"
os.makedirs(STATION_DIR, exist_ok=True)

# 1. 抓取氣象署最新資料 (以 O-A0001-001 自動氣象站為例)
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

            # 雨量處理：異常值留 None，正常 0 仍留 0.0
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

    # 若檔案存在則追加，否則建立新檔
    if os.path.exists(invalid_csv_path):
        exist_invalid_df = pd.read_csv(invalid_csv_path)
        invalid_df = pd.concat(
            [exist_invalid_df, invalid_df], ignore_index=True
        ).drop_duplicates()

    invalid_df.to_csv(invalid_csv_path, index=False, encoding="utf-8-sig")
    print(f"已整理無效/缺失數據至: {invalid_csv_path} (共 {len(invalid_df)} 筆)")
else:
    print("本次抓取無異常/缺失資料。")

# 2. 檢查歷史 CSV 並合併
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
            print(f"成功讀取舊歷史資料檔: {old_file}")
    except Exception as e:
        print(f"讀取 {old_file} 失敗: {e}")

all_incoming_df = pd.concat([old_records_df, new_df], ignore_index=True)

# 3. 按測站寫入各自獨立 CSV
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
    print(
        f"總彙整檔案 {master_filename} 更新完成，總計 {len(master_df)} 筆歷史紀錄。"
    )

# ==========================================
# 5. 自動繪製氣溫折線圖與雨量直條圖
# ==========================================
if master_list and not master_df.empty:
    plot_df = master_df.copy()

    plot_df["DateTime"] = pd.to_datetime(plot_df["DateTime"])
    plot_df["Temperature"] = pd.to_numeric(
        plot_df["Temperature"], errors="coerce"
    )
    plot_df["Rainfall"] = pd.to_numeric(plot_df["Rainfall"], errors="coerce")

    # --- 時間軸自主調整 (依據 START_DATE 與 END_DATE 進行過濾) ---
    if START_DATE:
        plot_df = plot_df[plot_df["DateTime"] >= pd.to_datetime(START_DATE)]
    if END_DATE:
        # 如果只給年月 (如 "2026-08")，轉換時包含該月最後一刻
        end_dt = pd.to_datetime(END_DATE)
        if len(END_DATE) <= 7:  # YYYY-MM 格式
            end_dt = end_dt + pd.offsets.MonthEnd(1) + pd.Timedelta(days=1)
        plot_df = plot_df[plot_df["DateTime"] <= end_dt]

    plot_df.sort_values(by="DateTime", inplace=True)

    if plot_df.empty:
        print("指定時間區間內沒有資料可供繪圖。")
    else:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

        station_names = plot_df["StationName"].unique()
        num_stations = len(station_names)

        # 1. 上圖：氣溫折線圖
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

        ax1.set_title("即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold")
        ax1.set_ylabel("氣溫 (°C)")
        ax1.grid(True, linestyle="--", alpha=0.5)
        ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

        # 2. 下圖：雨量直條圖
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

        ax2.set_title("即時雨量直條圖 (mm)", fontsize=14, fontweight="bold")
        ax2.set_xlabel("時間")
        ax2.set_ylabel("雨量 (mm)")
        ax2.grid(True, linestyle="--", alpha=0.5)
        ax2.legend(loc="upper left", bbox_to_anchor=(1, 1))

        # 設定 X 軸時間顯示格式
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=45)

        plt.tight_layout()

        chart_filename = "weather_chart.png"
        plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"氣溫折線圖與雨量直條圖繪製完成：{chart_filename}")
