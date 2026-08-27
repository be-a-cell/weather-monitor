import glob
import os
from pathlib import Path
import pandas as pd

# 取得專案根目錄 (weather-monitor/)
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "raw"
HISTORICAL_DIR = BASE_DIR / "historical_data"

HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)

# 測站 ID 與中文名稱對照表
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

    station_data_list = {}

    for file_path in raw_files:
        filename = file_path.name
        # 解析檔名 (例: C0Z220-2026-08-26.csv)
        try:
            station_id, date_str = filename.replace(".csv", "").split("-", 1)
        except ValueError:
            continue

        # 讀取氣象 CSV (header=1 自動抓取第二行的英文欄位名稱)
        df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")
        df.insert(0, "Station", station_id)
        df.insert(1, "Date", date_str)

        # 時間補零與 24 時跨夜邏輯修正
        df["ObsTime"] = df["ObsTime"].astype(str).str.zfill(2)
        df["Datetime"] = pd.to_datetime(
            date_str + " " + df["ObsTime"].replace({"24": "00"}),
            format="%Y-%m-%d %H",
        )
        df.loc[df["ObsTime"] == "24", "Datetime"] += pd.Timedelta(days=1)

        # 氣象異常符號清洗 (&, x 轉為空值；T 轉為微量雨量 0.05)
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

    # 寫入或追加至 historical_data/
    for station_id, df_list in station_data_list.items():
        new_df = pd.concat(df_list, ignore_index=True)

        st_name = STATION_MAP.get(station_id, "未知")
        out_name = f"{station_id}_{st_name}.csv"
        out_path = HISTORICAL_DIR / out_name

        # 若已存在歷史檔，先讀取並合併，最後依 Datetime 去重
        if out_path.exists():
            old_df = pd.read_csv(out_path)
            # 統一轉成 Datetime 格式比較
            old_df["Datetime"] = pd.to_datetime(old_df["Datetime"])
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        combined_df.sort_values(by="Datetime", inplace=True)
        combined_df.drop_duplicates(
            subset=["Datetime"], keep="last", inplace=True
        )

        combined_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"成功更新歷史資料檔：{out_path}")


if __name__ == "__main__":
    process_raw_files()
