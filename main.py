import os
import requests
import pandas as pd
import matplotlib.pyplot as plt

# 讀取氣象署 API (使用 O-A0003-001 自動氣象站資料)
API_KEY = os.environ.get("CWA_API_KEY")
URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001?Authorization={API_KEY}&format=JSON"
CSV_FILE = "weather_history.csv"

def fetch_weather_data():
    res = requests.get(URL)
    if res.status_code != 200:
        print(f"API 請求失敗，狀態碼：{res.status_code}")
        return None
    
    data = res.json()
    stations = data.get("records", {}).get("Station", [])
    
    records = []
    for s in stations:
        station_name = s.get("StationName")
        obs_time = s.get("ObsTime", {}).get("DateTime")
        
        # 氣溫 (AirTemperature)
        temp = s.get("WeatherElement", {}).get("AirTemperature", -99)
        # 1小時累積雨量 (Precipitation)
        rain = s.get("WeatherElement", {}).get("Now", {}).get("Precipitation", 0)
        
        # 過濾無效數值 (-99 代表測站故障/無數值)
        try:
            temp = float(temp) if float(temp) > -50 else None
        except:
            temp = None
            
        try:
            rain = float(rain) if float(rain) >= 0 else 0.0
        except:
            rain = 0.0

        records.append({
            "DateTime": pd.to_datetime(obs_time),
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
        combined_df = pd.concat([old_df, new_df]).drop_duplicates(subset=["DateTime", "StationName"])
    else:
        combined_df = new_df

    combined_df.sort_values("DateTime", inplace=True)
    combined_df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    print("CSV 資料庫更新成功！")

    # 2. 繪製氣溫與雨量圖表 (以資料最多的前 3 個測站為例)
    top_stations = combined_df["StationName"].value_counts().head(3).index.tolist()
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    for st in top_stations:
        st_data = combined_df[combined_df["StationName"] == st]
        ax1.plot(st_data["DateTime"], st_data["Temperature"], marker='o', label=st)
        ax2.plot(st_data["DateTime"], st_data["Rainfall"], marker='s', linestyle='--', label=st)

    ax1.set_ylabel("氣溫 (°C)")
    ax1.set_title("即時氣溫與雨量變化圖")
    ax1.grid(True)
    ax1.legend()

    ax2.set_ylabel("雨量 (mm)")
    ax2.set_xlabel("時間")
    ax2.grid(True)
    ax2.legend()

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("weather_chart.png")
    plt.close()
    print("統計圖表（weather_chart.png）更新成功！")

if __name__ == "__main__":
    update_csv_and_plot()
