import os
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
for station in data["records"]["Station"]:
    s_id = station["StationId"]
    if s_id in target_stations:
        s_name = station["StationName"]
        obs_time = station["ObsTime"]["DateTime"]

        # 抓取氣溫與雨量 (若為 -99 或 -998 代表無效值，改為 0 或 None)
        temp = station["WeatherElement"]["AirTemperature"]
        temp = float(temp) if temp not in [-99, -998, "-99", "-998"] else None

        rain = station["WeatherElement"]["Now"]["Precipitation"]
        rain = float(rain) if rain not in [-99, -998, "-99", "-998"] else 0.0

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
    # 合併舊資料與新資料
    combined_df = pd.concat([old_df, new_df], ignore_index=True)
else:
    combined_df = new_df

# 3. 關鍵去重步驟：依據「時間 + 測站ID」去除重複資料
combined_df.drop_duplicates(subset=["DateTime", "StationId"], inplace=True)

# 依時間與測站排序
combined_df.sort_values(by=["DateTime", "StationId"], inplace=True)

# 4. 覆蓋寫回 CSV
combined_df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
print("資料更新完成，共計", len(combined_df), "筆歷史紀錄。")
