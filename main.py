import os
import requests
import pandas as pd
import matplotlib.pyplot as plt

# 1. 你要監測的 6 個自動氣象站
TARGET_STATIONS = ["C0T9D0", "C0Z310", "C0Z220", "C0Z230", "C0TA40", "C0TA50"]

API_KEY = os.environ.get("CWA_API_KEY")
# 使用包含自動氣象站的 O-A0001-001 API
URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={API_KEY}&format=JSON"
CSV_FILE = "weather_history.csv"

# 設定 Matplotlib 中文字型
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
        print("未抓取到任何測站資料。")
        return None

    records = []
    for s in stations:
        station_id = s.get("StationId")
        
        # 篩選指定的 6 個測站
        if station_id in TARGET_STATIONS:
            station_name = s.get("StationName")
            
            # O-A0001-001 時間與氣象要素解析
            obs_time = s.get("ObsTime", {}).get("DateTime") or s.get("DateTime")
            weather_el = s.get("WeatherElement", {})
            
            # 取得氣溫 (AirTemperature)
            temp_val = weather_el.get("AirTemperature", -99)
            
            # 取得雨量 (Now -> Precipitation)
            rain_val = weather_el.get("Now", {}).get("Precipitation", 0)
            
            # 數值轉換與清理 (-99 代表無效值)
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
            
    print(f"成功篩選出 {len(records)} 筆指定測站資料。")
    return pd.DataFrame(records)

def update_csv_and_plot():
    new_df = fetch_weather_data()
    if new_df is None or new_df.empty:
        print("警告：未抓到指定測站資料。")
        return

    # 處理歷史 CSV：避免舊資料被覆蓋
    if os.path.exists(CSV_FILE):
        print("讀取現有 CSV 歷史紀錄並合併...")
        old_df = pd.read_csv(CSV_FILE)
        old_df["DateTime"] = pd.to_datetime(old_df["DateTime"])
        
        # 去除同一時間與同一測站的重複筆數
        combined_df = pd.concat([old_df, new_df]).drop_duplicates(subset=["DateTime", "StationId"])
    else:
        print("建立全新 CSV 紀錄檔...")
        combined_df = new_df

    combined_df.sort_values("DateTime", inplace=True)
    combined_df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    print(f"CSV 更新完成，目前累積總筆數：{len(combined_df)}")

    # 繪製指定的 6 個測站圖表 (氣溫 + 雨量)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    unique_stations = combined_df["StationName"].unique()
    for st in unique_stations:
        st_data = combined_df[combined_df["StationName"] == st]
        ax1.plot(st_data["DateTime"], st_data["Temperature"], marker='o', label=st)
        ax2.plot(st_data["DateTime"], st_data["Rainfall"], marker='s', linestyle='--', label=st)

    ax1.set_ylabel("氣溫 (°C)")
    ax1.set_title("指定自動氣象站即時氣溫與雨量監測圖")
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
    print("統計圖表（weather_chart.png）更新成功！")

if __name__ == "__main__":
    update_csv_and_plot()
