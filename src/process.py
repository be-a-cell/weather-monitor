import glob
import os
from pathlib import Path
import pandas as pd

# 取得專案根目錄 (weather-monitor/)
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "raw"
HISTORICAL_DIR = BASE_DIR / "historical_data"

HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)

# 測站 ID 與中文名稱對照表 (確保存入 historical_data 時有名稱)
STATION_MAP = {
    "C0TA40": "秀林",
    "C0TA50": "和仁",
    "C0Z310": "清水斷崖",
    "C0T9D0": "和中",
    "C0Z220": "和平林道",
    "C0Z230": "和平",
}


def process_raw_files():
    raw_files = list(RAW_DIR.glob("*.csv"))
    if not raw_files:
        print("未在 raw/ 目錄下發現 CSV 檔案。")
        return

    # 按測站分組收集資料
    station_data_list = {}

    for file_path in raw_files:
        filename = file_path.name
        # 解析檔名例: C0Z220-2026-08-26.csv
        try:
            station_id, date_str = filename.replace(".csv", "").split("-", 1)
        except ValueError:
            continue

        df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")
        df.insert(0, "Station", station_id)
        df.insert(1, "Date", date_str)

        # 處理 ObsTime 與 24 時跨夜邏輯
        df["ObsTime"] = df["ObsTime"].astype(str).str.zfill(2)
        df["Datetime"] = pd.to_datetime(
            date_str + " " + df["ObsTime"].replace({"24": "00"}),
            format="%Y-%m-%d %H",
        )
        df.loc[df["ObsTime"] == "24", "Datetime"] += pd.Timedelta(days=1)

        # 氣象異常值清洗
        df["Precp"] = df["Precp"].replace({"T": 0.05, "x": None, "&": None})
        num_cols = [
            "StnPres",
            "Temperature",
            "RH",
            "WS",
            "WD",
            "WSGust",
            "WDGust",
            "Precp",
        ]
        df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")

        if station_id not in station_data_list:
            station_data_list[station_id] = []
        station_data_list[station_id].append(df)

    # 寫入 historical_data/ 資料夾
    for station_id, df_list in station_data_list.items():
        combined_df = pd.concat(df_list, ignore_index=True)
        combined_df.sort_values(by="Datetime", inplace=True)
        combined_df.drop_duplicates(subset=["Datetime"], inplace=True)

        st_name = STATION_MAP.get(station_id, "未知")
        out_name = f"{station_id}_{st_name}.csv"
        out_path = HISTORICAL_DIR / out_name

        # 若已存在舊歷史檔則進行合併去重
        if out_path.exists():
            old_df = pd.read_csv(out_path)
            combined_df = pd.concat([old_df, combined_df], ignore_index=True)
            combined_df.drop_duplicates(
                subset=["Datetime"], keep="last", inplace=True
            )

        combined_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"已更新歷史資料：{out_path}")


if __name__ == "__main__":
    process_raw_files()
