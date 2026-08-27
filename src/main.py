import glob
import os
from pathlib import Path
import matplotlib as mpl
import matplotlib.dates as mdates
from matplotlib import font_manager
import matplotlib.pyplot as plt
import pandas as pd
import requests

# ==========================================
# 0. 路徑與基礎設定 (適應 src/ 結構)
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_DIR = BASE_DIR / "config"
STATION_DIR = BASE_DIR / "stations_data"
HISTORICAL_DIR = BASE_DIR / "historical_data"

STATION_DIR.mkdir(parents=True, exist_ok=True)
HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------
# 徹底修復中文字型 (豆腐塊問題)
# ------------------------------------------
FONT_PATH = CONFIG_DIR / "NotoSansCJKtc-Regular.otf"
chosen_font_prop = None

# 1. 嘗試載入本地 otf
if FONT_PATH.exists():
    try:
        font_manager.fontManager.addfont(str(FONT_PATH))
        chosen_font_prop = font_manager.FontProperties(fname=str(FONT_PATH))
        mpl.rcParams["font.family"] = chosen_font_prop.get_name()
        print(f"成功載入本地字型: {FONT_PATH}")
    except Exception as e:
        print(f"本地字型載入失敗 ({e})，準備搜尋系統字型...")

# 2. 若本地字型不可用，搜尋 Linux / Ubuntu 系統安裝的中文字型
if chosen_font_prop is None:
    system_fonts = font_manager.findSystemFonts(fontpaths=None, fontext="ttf")
    cjk_fonts = [
        f
        for f in system_fonts
        if any(
            k in Path(f).name.lower()
            for k in ["notosanscjk", "wqy", "zenhei", "microhei", "kai", "ming"]
        )
    ]
    if cjk_fonts:
        chosen_font_prop = font_manager.FontProperties(fname=cjk_fonts[0])
        mpl.rcParams["font.family"] = chosen_font_prop.get_name()
        print(f"成功套用系統中文字型: {cjk_fonts[0]}")
    else:
        # 備用回退設定
        mpl.rcParams["font.sans-serif"] = [
            "Noto Sans CJK TC",
            "Noto Sans TC",
            "WenQuanYi Micro Hei",
            "DejaVu Sans",
        ]
        chosen_font_prop = font_manager.FontProperties(
            family=["Noto Sans CJK TC", "DejaVu Sans"]
        )

mpl.rcParams["axes.unicode_minus"] = False

# ==========================================
# 輔助函式：標準化 CSV 欄位名稱 (修復時區衝突與重複欄位)
# ==========================================
def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """清理並統一不同來源 CSV 的欄位名稱與格式，統一移除時區資訊"""
    if df.empty:
        return df

    # 清除欄位前後空白
    df.columns = [str(c).strip() for c in df.columns]

    # 針對欄位對映進行處理
    rename_map = {}
    for col in df.columns:
        c_lower = col.lower()
        if "stationid" in c_lower or c_lower == "station_id":
            rename_map[col] = "station_id"
        elif "stationname" in c_lower or c_lower == "station_name":
            rename_map[col] = "station_name"
        elif "datetime" in c_lower or c_lower == "obs_time":
            rename_map[col] = "datetime"
        elif "temp" in c_lower or c_lower == "temperature":
            rename_map[col] = "temperature"
        elif "rain" in c_lower:
            rename_map[col] = "rainfall"

    df = df.rename(columns=rename_map)

    # 若重命名後有重複欄位名，僅保留第一個
    df = df.loc[:, ~df.columns.duplicated()]

    # 確保所需標準欄位均存在
    required_cols = [
        "station_id",
        "station_name",
        "datetime",
        "temperature",
        "rainfall",
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # 只保留標準欄位
    df = df[required_cols].copy()

    # 資料型態轉型與【時區統一處理】
    df["datetime"] = pd.to_datetime(
        df["datetime"], errors="coerce"
    )  # 轉為 Timestamp

    # 關鍵修正：若包含時區資訊，則統一移除時區標籤 (Convert tz-aware to tz-naive)
    if (
        pd.api.types.is_datetime64tz_dtype(df["datetime"])
        or df["datetime"].dt.tz is not None
    ):
        df["datetime"] = df["datetime"].dt.tz_localize(None)

    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["rainfall"] = pd.to_numeric(df["rainfall"], errors="coerce")

    # 移除無效時間
    df = df.dropna(subset=["datetime"])

    return df


# ==========================================
# 1. 抓取氣象署 API 資料
# ==========================================
API_KEY = os.getenv("CWA_API_KEY")
url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={API_KEY}"

target_stations = ["C0TA40", "C0TA50", "C0Z310", "C0T9D0", "C0Z220", "C0Z230"]
new_records = []
invalid_records = []

try:
    response = requests.get(url, timeout=10)
    data = response.json()
except Exception as e:
    print(f"API 請求失敗: {e}")
    data = {}

if "records" in data and "Station" in data["records"]:
    for station in data["records"]["Station"]:
        s_id = station.get("StationId")
        if s_id in target_stations:
            s_name = station.get("StationName", "未知測站")
            obs_time = station.get("ObsTime", {}).get("DateTime", "")
            weather_elem = station.get("WeatherElement", {})

            raw_temp = weather_elem.get("AirTemperature")
            temp_is_invalid = raw_temp in [
                None,
                -99,
                -998,
                "-99",
                "-998",
                "None",
            ]
            temp = float(raw_temp) if not temp_is_invalid else None

            raw_rain = weather_elem.get("Now", {}).get("Precipitation")
            rain_is_invalid = raw_rain in [
                None,
                -99,
                -998,
                "-99",
                "-998",
                "None",
            ]
            rain = float(raw_rain) if not rain_is_invalid else None

            if temp_is_invalid or rain_is_invalid:
                invalid_records.append(
                    {
                        "datetime": obs_time,
                        "station_id": s_id,
                        "station_name": s_name,
                        "raw_temperature": raw_temp,
                        "raw_rainfall": raw_rain,
                        "issue": (
                            "氣溫異常"
                            if temp_is_invalid and not rain_is_invalid
                            else (
                                "雨量異常"
                                if rain_is_invalid and not temp_is_invalid
                                else "氣溫與雨量皆異常"
                            )
                        ),
                    }
                )

            new_records.append(
                {
                    "station_id": s_id,
                    "station_name": s_name,
                    "datetime": obs_time,
                    "temperature": temp,
                    "rainfall": rain if rain is not None else 0.0,
                }
            )

new_df = normalize_dataframe(pd.DataFrame(new_records))

# 記錄異常資料
if invalid_records:
    invalid_df = pd.DataFrame(invalid_records)
    invalid_csv_path = BASE_DIR / "missing_or_invalid_data.csv"
    if invalid_csv_path.exists() and invalid_csv_path.stat().st_size > 0:
        try:
            exist_invalid_df = pd.read_csv(invalid_csv_path)
            invalid_df = pd.concat(
                [exist_invalid_df, invalid_df], ignore_index=True
            ).drop_duplicates()
        except Exception:
            pass
    invalid_df.to_csv(invalid_csv_path, index=False, encoding="utf-8-sig")

# ==========================================
# 2. 獨立測站數據更新與寫入 (整合 historical_data)
# ==========================================
for s_id in target_stations:
    station_incoming = (
        new_df[new_df["station_id"] == s_id].copy()
        if not new_df.empty
        else pd.DataFrame()
    )

    # 1. 讀取 historical_data/ 下對應的 CSV
    history_matches = list(HISTORICAL_DIR.glob(f"{s_id}_*.csv"))
    historical_df = pd.DataFrame()
    if history_matches:
        hist_file = history_matches[0]
        if hist_file.stat().st_size > 0:
            try:
                raw_hdf = pd.read_csv(hist_file)
                historical_df = normalize_dataframe(raw_hdf)
            except Exception as e:
                print(f"讀取歷史檔案 {hist_file.name} 失敗: {e}")

    # 2. 讀取 stations_data/ 下對應的 CSV
    station_matches = list(STATION_DIR.glob(f"{s_id}_*.csv"))
    exist_df = pd.DataFrame()
    if station_matches:
        exist_file = station_matches[0]
        if exist_file.stat().st_size > 0:
            try:
                raw_edf = pd.read_csv(exist_file)
                exist_df = normalize_dataframe(raw_edf)
            except Exception as e:
                print(f"讀取既有檔案 {exist_file.name} 失敗: {e}")

    # 3. 合併舊歷史、已有資料與 API 新資料
    combined_station_df = pd.concat(
        [historical_df, exist_df, station_incoming], ignore_index=True
    )

    if combined_station_df.empty:
        continue

    # 【關鍵修正】強制將這個檔的所有 station_id 校正為正確的 s_id (如 C0Z310)
    combined_station_df["station_id"] = s_id

    # 規範化處理與去除重複項目
    combined_station_df.drop_duplicates(
        subset=["station_id", "datetime"], inplace=True
    )
    combined_station_df.sort_values(by="datetime", inplace=True)

    # 格式化 datetime 為字串再存檔
    combined_station_df["datetime"] = combined_station_df[
        "datetime"
    ].dt.strftime("%Y-%m-%d %H:%M:%S")

    s_name = combined_station_df["station_name"].dropna().iloc[0]
    station_csv_path = STATION_DIR / f"{s_id}_{s_name}.csv"

    combined_station_df.to_csv(
        station_csv_path, index=False, encoding="utf-8-sig"
    )

# ==========================================
# 3. 彙整歷史總表 weather_history.csv (存放在根目錄)
# ==========================================
all_station_files = list(STATION_DIR.glob("*.csv"))
master_list = []

for f in all_station_files:
    if f.stat().st_size > 0:
        try:
            raw_f = pd.read_csv(f)
            norm_f = normalize_dataframe(raw_f)
            if not norm_f.empty:
                master_list.append(norm_f)
        except Exception as e:
            print(f"彙整總表時讀取 {f.name} 失敗: {e}")

master_df = pd.DataFrame()
if master_list:
    master_df = pd.concat(master_list, ignore_index=True)
    master_df.drop_duplicates(subset=["station_id", "datetime"], inplace=True)
    master_df.sort_values(by=["datetime", "station_id"], inplace=True)

    # 格式化日期並匯出總表
    export_master_df = master_df.copy()
    export_master_df["datetime"] = export_master_df["datetime"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    export_master_df.to_csv(
        BASE_DIR / "weather_history.csv", index=False, encoding="utf-8-sig"
    )
    print(f"成功更新總表 weather_history.csv，共 {len(export_master_df)} 筆資料。")

# ==========================================
# 4. 繪製圖表 (輸出至根目錄 weather_chart.png)
# ==========================================
if not master_df.empty:
    plot_df = master_df.copy()
    plot_df["StationLabel"] = (
        plot_df["station_id"] + " " + plot_df["station_name"]
    )
    plot_df.sort_values(by="datetime", inplace=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    station_labels = plot_df["StationLabel"].unique()
    num_stations = len(station_labels)

    # 【上圖】氣溫折線圖
    for label in station_labels:
        group = plot_df[plot_df["StationLabel"] == label].dropna(
            subset=["temperature"]
        )
        if group.empty:
            continue
        ax1.plot(
            group["datetime"],
            group["temperature"],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=label,
        )

    t_title = ax1.set_title("即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold")
    t_ylabel = ax1.set_ylabel("氣溫 (°C)", fontsize=12)
    ax1.grid(True, linestyle="--", alpha=0.5)
    leg1 = ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # 【下圖】雨量直條圖
    single_bar_width = 0.012 / max(num_stations, 1)

    for i, label in enumerate(station_labels):
        group = plot_df[plot_df["StationLabel"] == label].dropna(
            subset=["rainfall"]
        )
        if group.empty:
            continue

        offset = (i - (num_stations - 1) / 2) * single_bar_width
        x_dates = mdates.date2num(group["datetime"]) + offset

        ax2.bar(
            x_dates,
            group["rainfall"],
            width=single_bar_width,
            alpha=0.7,
            label=label,
        )

    r_title = ax2.set_title("即時雨量直條圖 (mm)", fontsize=14, fontweight="bold")
    r_xlabel = ax2.set_xlabel("時間 (DateTime)", fontsize=12)
    r_ylabel = ax2.set_ylabel("雨量 (mm)", fontsize=12)
    ax2.grid(True, linestyle="--", alpha=0.5)
    leg2 = ax2.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # X 軸時間軸格式設定
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.autofmt_xdate(rotation=45)

    # 顯式為圖表上所有中文元件指定字型 Properties (徹底告別豆腐塊)
    if chosen_font_prop:
        t_title.set_fontproperties(chosen_font_prop)
        t_ylabel.set_fontproperties(chosen_font_prop)
        r_title.set_fontproperties(chosen_font_prop)
        r_xlabel.set_fontproperties(chosen_font_prop)
        r_ylabel.set_fontproperties(chosen_font_prop)

        for text in leg1.get_texts():
            text.set_fontproperties(chosen_font_prop)
        for text in leg2.get_texts():
            text.set_fontproperties(chosen_font_prop)

        for ax in [ax1, ax2]:
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontproperties(chosen_font_prop)

    plt.tight_layout()

    chart_filename = BASE_DIR / "weather_chart.png"
    plt.savefig(chart_filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"圖表已成功生成: {chart_filename}")
