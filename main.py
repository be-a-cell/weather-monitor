import os
import requests
import pandas as pd
import matplotlib.pyplot as plt

# 指定要抓取的測站列表
STATION_IDS = "C0T9D0,C0Z310,C0Z220,C0Z230,C0TA40,C0TA50"
API_KEY = os.environ.get("CWA_API_KEY")

# API URL 加上 StationId 篩選
URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001?Authorization={API_KEY}&format=JSON&StationId={STATION_IDS}"
CSV_FILE = "weather_history.csv"

# 設定 Matplotlib 字型 (支援 Linux 伺服器中文)
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK TC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def fetch_weather_data():
    res = requests.get(URL)
    if res.status_code != 200:
        print(f"API 請求失敗，狀態碼：{res.status_code}")
        return None
    
    data = res.json()
    stations = data.get("records", {}).get("Station", [])
    
    if not stations:
        print("未抓取到指定測站資料。")
        return None

    records = []
    for s in stations:
        station_id = s.get("StationId")
        station_name = s.get("StationName")
        
        # 取得觀測時間
        obs_time = s.get("ObsTime", {}).get("DateTime") or s.get("DateTime")
        
        # 取得 WeatherElement 內的數據
        weather_el = s.get("WeatherElement", {})
        
        # 氣溫 (AirTemperature)
        temp_val = weather_el.get("AirTemperature", -99)
        # 1小時累積雨量 (Now -> Precipitation)
        rain_val = weather_el.get("Now", {}).get("Precipitation", 0)
        
        # 數值清理與轉換
        try:
            temp = float(temp_val) if float(temp_val) > -50 else None
        except (ValueError, TypeError):
            temp = None
            
        try:
            rain = float(rain_val) if float(rain_val) >= 0 else 0.0
        except (ValueError, TypeError):
            rain = 0.0

        records.append({
            "DateTime": pd.to_datetime(obs_time),
            "StationId": station_id,
            "StationName": station_name,
            "Temperature": temp,
            "Rainfall": rain
        })
    return pd.DataFrame(records)

def update_csv_and_plot():
    new_df = fetch_weather_data()
    if new_df is None or new_df.empty:
        print("未抓到有效資料。")
        return

    # 1. 更新或建立 CSV 歷史紀錄
    if os.path.exists(CSV_FILE):
        old_df = pd.read_csv(CSV_FILE, parse_dates=["DateTime"])
        combined_df = pd.concat([old_df, new_df]).drop_duplicates(subset=["DateTime", "StationId"])
    else:
        combined_df = new_df

    combined_df.sort_values("DateTime", inplace=True)
    combined_df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    print("CSV 資料庫更新成功！")

    # 2. 繪製指定的 6 個測站圖表
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # 取出所有登場過的測站
    target_stations = combined_df["StationName"].unique()
    
    for st in target_stations:
        st_data = combined_df[combined_df["StationName"] == st]
        ax1.plot(st_data["DateTime"], st_data["Temperature"], marker='o', label=st)
        ax2.plot(st_data["DateTime"], st_data["Rainfall"], marker='s', linestyle='--', label=st)

    ax1.set_ylabel("氣溫 (°C)")
    ax1.set_title("指定測站即時氣溫與雨量變化圖")
    ax1.grid(True)
    ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

    ax2.set_ylabel("雨量 (mm)")
    ax2.set_xlabel("時間")
    ax2.grid(True)
    ax2.legend(loc="upper left", bbox_to_anchor=(1, 1))

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("weather_chart.png")
    plt.close()
    print("指定測站統計圖表（weather_chart.png）更新成功！")

if __name__ == "__main__":
    update_csv_and_plot()
