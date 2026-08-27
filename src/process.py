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


def standardize_datetime(df):
    """將 datetime 欄位統一轉換為 ISO 標準時間格式 (YYYY-MM-DD HH:MM:SS)"""
    if "datetime" in df.columns:
        # 1. 自動解析混雜格式 (/ 與 -, 有無時間欄位皆可處理)
        dt_series = pd.to_datetime(
            df["datetime"].astype(str).str.strip(),
            format="mixed",
            errors="coerce",
        )

        # 2. 統一轉為字串格式 YYYY-MM-DD HH:MM:SS
        df["datetime"] = dt_series.dt.strftime("%Y-%m-%d %H:%M:%S")

    return df
    
def clean_raw_df(file_path):
    filename = file_path.name
    try:
        station_id, date_str = filename.replace(".csv", "").split("-", 1)
    except ValueError:
        return None, None

    # header=1 跳過第一行中文單位，直接使用第二行英文欄位
    df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")

    # ObsTime 補零並處理 24 時跨夜邏輯
    df["ObsTime"] = df["ObsTime"].astype(str).str.zfill(2)
    dt_series = pd.to_datetime(
        date_str + " " + df["ObsTime"].replace({"24": "00"}),
        format="%Y-%m-%d %H",
        errors="coerce",
    )
    # 若時間為 24 時，日期自動加 1 天
    dt_series.loc[df["ObsTime"] == "24"] += pd.Timedelta(days=1)
    df["datetime"] = dt_series.dt.strftime("%Y-%m-%d %H:%M:%S")

    # 欄位建構與重命名
    df["station_id"] = station_id
    df["station_name"] = STATION_MAP.get(station_id, "未知")
    df.rename(
        columns={"Temperature": "temperature", "Precp": "rainfall"},
        inplace=True,
    )

    # 氣象異常值與微量降雨清洗 (T 轉 0.05, 異常字元轉 NaN)
    df["rainfall"] = df["rainfall"].replace({"T": 0.05, "x": None, "&": None})

    # 數值轉型
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
            # 確保欄位名稱皆為小寫相容
            old_df.columns = [c.lower() for c in old_df.columns]
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        # 強制維持指定 Schema 欄位順序與資料結構
        combined_df = combined_df[TARGET_COLUMNS]
        combined_df.sort_values(by="datetime", inplace=True)
        combined_df.drop_duplicates(
            subset=["datetime"], keep="last", inplace=True
        )

        combined_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"成功更新歷史資料（Schema 統整完畢）：{out_path}")


if __name__ == "__main__":
    process_raw_files()
