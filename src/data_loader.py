import json
import os
from pathlib import Path
import pandas as pd

# ==========================================
# 0. 路徑與基礎設定 (適應 src/ 結構)
# ==========================================
# 強制設定為專案根目錄 (weather-monitor/)
BASE_DIR = Path(__file__).resolve().parent.parent

# 統一動態路徑
CONFIG_DIR = BASE_DIR / "config"
RAW_DIR = BASE_DIR / "raw"
HISTORICAL_DIR = BASE_DIR / "historical_data"
STATIONS_DIR = BASE_DIR / "stations_data"
FONT_PATH = CONFIG_DIR / "NotoSansCJKtc-Regular.otf"


# ==========================================
# 1. 記憶設定讀取與儲存 (存放於 config/ 目錄)
# ==========================================
def load_settings():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"讀取設定檔失敗: {e}")

    return {
        "station": "秀林",
        "start_date": "2024-01-01",
        "end_date": "2026-12-31",
        "temp_color": "#EF553B",
        "rain_color": "#636EFA",
    }


def save_settings(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


# ==========================================
# 2. 自動合併歷史與即時測站資料
# ==========================================
def load_all_weather_data():
    all_dfs = []

    # 搜尋 historical_data/ 與 stations_data/ 兩個資料夾
    search_dirs = [HISTORICAL_DIR, STATIONS_DIR]

    for target_dir in search_dirs:
        if target_dir.exists():
            for csv_file in target_dir.glob("*.csv"):
                try:
                    df = pd.read_csv(csv_file)

                    # 欄位大小寫彈性相容轉換
                    col_map = {
                        "DateTime": "datetime",
                        "StationId": "station_id",
                        "StationName": "station_name",
                        "Temperature": "temperature",
                        "Rainfall": "rainfall",
                    }
                    df.rename(columns=col_map, inplace=True)

                    if "datetime" in df.columns:
                        df["datetime"] = pd.to_datetime(df["datetime"])
                        all_dfs.append(df)
                except Exception as e:
                    print(f"讀取資料檔 {csv_file.name} 失敗: {e}")

    if not all_dfs:
        return pd.DataFrame()

    # 合併並去除重複資料
    df_combined = pd.concat(all_dfs, ignore_index=True)

    subset_cols = [
        col for col in ["station_id", "datetime"] if col in df_combined.columns
    ]
    if subset_cols:
        df_combined = df_combined.drop_duplicates(subset=subset_cols)

    if "datetime" in df_combined.columns:
        df_combined = df_combined.sort_values(by="datetime")

    return df_combined
