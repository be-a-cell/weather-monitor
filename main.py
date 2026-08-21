import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import requests

# 1. 抓取氣象署資料 (以 O-A0001-001 自動氣象站為例)
API_KEY = os.getenv("CWA_API_KEY")
url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={API_KEY}"

response = requests.get(url)
data = response.json()

target_stations = ["C0TA40", "C0TA50", "C0Z310", "C0T9D0", "C0Z220", "C0Z230"]
new_records = []

# 解析目標測站
if "records" in data and "Station" in data["records"]:
    for station in data["records"]["Station"]:
        s_id = station["StationId"]
        if s_id in target_stations:
            s_name = station["StationName"]
            obs_time = station["ObsTime"]["DateTime"]

            # 抓取氣溫與雨量 (若為 -99 或 -998 代表無效值，改為 0 或 None)
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

# 2. 合併歷史資料
csv_filename = "weather_history.csv"

if os.path.exists(csv_filename):
    old_df = pd.read_csv(csv_filename)
    combined_df = pd.concat([old_df, new_df], ignore_index=True)
else:
    combined_df = new_df

# 3. 關鍵去重與排序：依據「時間 + 測站ID」去除重複資料
combined_df.drop_duplicates(subset=["DateTime", "StationId"], inplace=True)
combined_df.sort_values(by=["DateTime", "StationId"], inplace=True)

# 4. 覆蓋寫回 CSV
combined_df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
print("資料更新完成，共計", len(combined_df), "筆歷史紀錄。")

# ==========================================
# 5. 自動繪製溫度與雨量折線圖並輸出為圖片
# ==========================================
if not combined_df.empty:
    # 解決 Linux (GitHub Actions) 上的中文字體顯示問題
    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK TC",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
    ]
    plt.rcParams["axes.unicode_minus"] = False  # 正常顯示負號

    # 複製份資料處理時間格式
    plot_df = combined_df.copy()
    plot_df["DateTime"] = pd.to_datetime(plot_df["DateTime"])

    # 建立 2 個上下子圖 (上方：溫度，下方：雨量)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # 依測站分組繪圖
    for station_name, group in plot_df.groupby("StationName"):
        # 溫度折線圖
        ax1.plot(
            group["DateTime"],
            group["Temperature"],
            marker="o",
            markersize=3,
            label=station_name,
        )
        # 雨量折線圖
        ax2.plot(
            group["DateTime"],
            group["Rainfall"],
            marker="s",
            markersize=3,
            label=station_name,
        )

    # 上圖 (氣溫) 設定
    ax1.set_title("即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold")
    ax1.set_ylabel("氣溫 (°C)")
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # 下圖 (雨量) 設定
    ax2.set_title("即時雨量變化圖 (mm)", fontsize=14, fontweight="bold")
    ax2.set_xlabel("時間")
    ax2.set_ylabel("雨量 (mm)")
    ax2.grid(True, linestyle="--", alpha=0.6)

    # 格式化 X 軸時間顯示 (例如：08-21 16:00)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate(rotation=45)

    plt.tight_layout()

    # 存檔至根目錄
    chart_filename = "weather_chart.png"
    plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"折線圖更新完成：{chart_filename}")
