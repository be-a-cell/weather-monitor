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

# 統一目標 Schema 欄位名稱
TARGET_COLUMNS = [
    "station_id",
    "station_name",
    "datetime",
    "temperature",
    "rainfall",
]


def clean_raw_df(file_path):
    filename = file_path.name
    try:
        station_id, date_str = filename.replace(".csv", "").split("-", 1)
    except ValueError:
        return None, None

    # 1. 讀取 CSV，使用 header=1 抓取第二行英文標頭
    df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")

    # 清洗欄位名稱：去除雙引號、前後空格並統一改為小寫
    df.columns = (
        df.columns.astype(str).str.replace('"', "").str.strip().str.lower()
    )

    # 如果 header=1 讀不到關鍵欄位，嘗試以 header=0 重新讀取
    if not any(
        col in df.columns for col in ["obstime", "time", "觀測時間(hour)"]
    ):
        df = pd.read_csv(file_path, header=0, encoding="utf-8-sig")
        df.columns = (
            df.columns.astype(str).str.replace('"', "").str.strip().str.lower()
        )

    # 2. 時間欄位辨識 (obstime)
    time_col = None
    for col in df.columns:
        if "obstime" in col or "time" in col or "觀測時間" in col:
            time_col = col
            break

    if not time_col:
        print(f"警告：檔案 {filename} 無法識別時間欄位，跳過處理。")
        return None, None

    # 清理資料內容中的雙引號與空格
    df = df.applymap(
        lambda x: str(x).replace('"', "").strip() if pd.notnull(x) else x
    )

    # ObsTime 補零與 24 時跨夜邏輯
    obs_time = df[time_col].astype(str).str.zfill(2)
    dt_series = pd.to_datetime(
        date_str + " " + obs_time.replace({"24": "00"}),
        format="%Y-%m-%d %H",
        errors="coerce",
    )
    dt_series.loc[obs_time == "24"] += pd.Timedelta(days=1)
    df["datetime"] = dt_series.dt.strftime("%Y-%m-%d %H:%M:%S")

    # 3. 氣溫欄位辨識 (temperature / temp / 氣溫)
    temp_col = None
    for col in df.columns:
        if "temperature" in col or "temp" in col or "氣溫" in col:
            temp_col = col
            break

    # 4. 雨量欄位辨識 (precp / rain / 降水 / 雨量)
    rain_col = None
    for col in df.columns:
        if "precp" in col or "rain" in col or "降水" in col or "雨量" in col:
            rain_col = col
            break

    df["temperature"] = df[temp_col] if temp_col else None
    df["rainfall"] = df[rain_col] if rain_col else None

    # 欄位建構
    df["station_id"] = station_id
    df["station_name"] = STATION_MAP.get(station_id, "未知")

    # 氣象異常符號清洗 (T 轉 0.05, 異常字元轉 NaN)
    if "rainfall" in df.columns:
        df["rainfall"] = df["rainfall"].replace(
            {"T": 0.05, "x": None, "&": None}
        )

    # 數值強制轉型
    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["rainfall"] = pd.to_numeric(df["rainfall"], errors="coerce")

    # 僅留存指定 Schema 欄位
    return station_id, df[TARGET_COLUMNS]


def process_raw_files():
    raw_files = list(RAW_DIR.glob("*.csv"))
    if not raw_files:
        print("未在 raw/ 目錄下發現 CSV 檔案。")
        return

    station_data_list = {}
    for file_path in raw_files:
        st_id, df_cleaned = clean_raw_df(file_path)
        if df_cleaned is not None:
            if st_id not in station_data_list:
                station_data_list[st_id] = []
            station_data_list[st_id].append(df_cleaned)

    # 寫入/追加至 historical_data/
    for station_id, df_list in station_data_list.items():
        new_df = pd.concat(df_list, ignore_index=True)
        st_name = STATION_MAP.get(station_id, "未知")
        out_name = f"{station_id}_{st_name}.csv"
        out_path = HISTORICAL_DIR / out_name

        if out_path.exists():
            old_df = pd.read_csv(out_path)
            old_df.columns = [c.lower() for c in old_df.columns]
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        # 強制維護指定 Schema 欄位順序與資料結構
        combined_df = combined_df[TARGET_COLUMNS]
        combined_df.sort_values(by="datetime", inplace=True)
        combined_df.drop_duplicates(
            subset=["datetime"], keep="last", inplace=True
        )

        combined_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"成功更新歷史資料：{out_path}")


if __name__ == "__main__":
    process_raw_files()
