import glob
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import requests

# 建立放置各測站獨立 CSV 的資料夾
STATION_DIR = "stations_data"
os.makedirs(STATION_DIR, exist_ok=True)

# 1. 抓取氣象署最新資料 (以 O-A0001-001 自動氣象站為例)
API_KEY = os.getenv("CWA_API_KEY")
url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={API_KEY}"

response = requests.get(url)
data = response.json()

target_stations = ["C0TA40", "C0TA50", "C0Z310", "C0T9D0", "C0Z220", "C0Z230"]
new_records = []

if "records" in data and "Station" in data["records"]:
    for station in data["records"]["Station"]:
        s_id = station["StationId"]
        if s_id in target_stations:
            s_name = station["StationName"]
            obs_time = station["ObsTime"]["DateTime"]

            # 氣溫與雨量清洗
            temp = station["WeatherElement"]["AirTemperature"]
            temp = (
                float(temp) if temp not in [-99, -998, "-99", "-998"] else None
            )

            rain = station["WeatherElement"]["Now"]["Precipitation"]
            rain = (
                float(rain) if rain not in [-99, -998, "-99", "-998"] else 0.0
            )

            new_records.append(
                {
                    "DateTime": obs_time,
                    "StationId": s_id,
                    "StationName": s_name,
                    "Temperature": temp,
                    "Rainfall": rain,
                }
            )

new_df = pd.DataFrame(new_records)

# 2. 檢查是否有舊的歷史 CSV 需要一併匯入 (例如 old_data.csv 或 舊的 weather_history.csv)
old_records_df = pd.DataFrame()
# 搜尋當前目錄下所有的歷史 CSV (排除總表與測站目錄)
historical_files = [
    f
    for f in glob.glob("*.csv")
    if f not in ["weather_history.csv"] and not f.startswith("stations_data")
]

for old_file in historical_files:
    try:
        temp_df = pd.read_csv(old_file)
        # 確保必要欄位存在
        if "StationId" in temp_df.columns and "DateTime" in temp_df.columns:
            # 只篩選目標 6 個測站
            temp_df = temp_df[temp_df["StationId"].isin(target_stations)]
            old_records_df = pd.concat(
                [old_records_df, temp_df], ignore_index=True
            )
            print(f"成功讀取舊歷史資料檔: {old_file}")
    except Exception as e:
        print(f"讀取 {old_file} 失敗: {e}")

# 合併本次最新抓取的資料與找到的舊 CSV 資料
all_incoming_df = pd.concat([old_records_df, new_df], ignore_index=True)

# 3. 按測站寫入各自獨立的 CSV 檔案 (例如：stations_data/C0TA40_秀林.csv)
for s_id in target_stations:
    # 篩選該測站資料
    station_incoming = all_incoming_df[
        all_incoming_df["StationId"] == s_id
    ].copy()

    if station_incoming.empty:
        # 如果這次沒抓到且沒舊資料，嘗試獲取測站名稱
        continue

    s_name = station_incoming["StationName"].iloc[0]
    station_csv_path = os.path.join(STATION_DIR, f"{s_id}_{s_name}.csv")

    # 如果該測站已有自己的獨立 CSV，讀取出來疊加
    if os.path.exists(station_csv_path):
        exist_df = pd.read_csv(station_csv_path)
        combined_station_df = pd.concat(
            [exist_df, station_incoming], ignore_index=True
        )
    else:
        combined_station_df = station_incoming

    # 去重 (依時間與測站ID) 並排序
    combined_station_df.drop_duplicates(
        subset=["DateTime", "StationId"], inplace=True
    )
    combined_station_df.sort_values(by="DateTime", inplace=True)

    # 寫回該測站專屬的 CSV
    combined_station_df.to_csv(
        station_csv_path, index=False, encoding="utf-8-sig"
    )
    print(f"測站 [{s_name}] 獨立 CSV 更新完成，共 {len(combined_station_df)} 筆。")

# 4. 統一彙整所有測站獨立 CSV $\rightarrow$ 輸出成總表 weather_history.csv
all_station_files = glob.glob(os.path.join(STATION_DIR, "*.csv"))
master_list = []

for s_file in all_station_files:
    m_df = pd.read_csv(s_file)
    master_list.append(m_df)

if master_list:
    master_df = pd.concat(master_list, ignore_index=True)
    master_df.drop_duplicates(
        subset=["DateTime", "StationId"], inplace=True
    )
    master_df.sort_values(by=["DateTime", "StationId"], inplace=True)

    master_filename = "weather_history.csv"
    master_df.to_csv(master_filename, index=False, encoding="utf-8-sig")
    print(
        f"總彙整檔案 {master_filename} 更新完成，總計 {len(master_df)} 筆歷史紀錄。"
    )

# 5. 自動繪製溫度與雨量折線圖並輸出為圖片
if master_list and not master_df.empty:
    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK TC",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    plot_df = master_df.copy()
    plot_df["DateTime"] = pd.to_datetime(plot_df["DateTime"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    for station_name, group in plot_df.groupby("StationName"):
        ax1.plot(
            group["DateTime"],
            group["Temperature"],
            marker="o",
            markersize=3,
            label=station_name,
        )
        ax2.plot(
            group["DateTime"],
            group["Rainfall"],
            marker="s",
            markersize=3,
            label=station_name,
        )

    ax1.set_title("即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold")
    ax1.set_ylabel("氣溫 (°C)")
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

    ax2.set_title("即時雨量變化圖 (mm)", fontsize=14, fontweight="bold")
    ax2.set_xlabel("時間")
    ax2.set_ylabel("雨量 (mm)")
    ax2.grid(True, linestyle="--", alpha=0.6)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate(rotation=45)

    plt.tight_layout()

    chart_filename = "weather_chart.png"
    plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"折線圖更新完成：{chart_filename}")
