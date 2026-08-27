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
# 中文字型設定
# ------------------------------------------
FONT_PATH = CONFIG_DIR / "NotoSansCJKtc-Regular.otf"
chosen_font_prop = None

if FONT_PATH.exists():
    try:
        font_manager.fontManager.addfont(str(FONT_PATH))
        chosen_font_prop = font_manager.FontProperties(fname=str(FONT_PATH))
        mpl.rcParams["font.family"] = chosen_font_prop.get_name()
        print(f"成功載入本地字型: {FONT_PATH}")
    except Exception as e:
        print(f"本地字型載入失敗 ({e})，準備搜尋系統字型...")

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
# 輔助函式：標準化 CSV 欄位名稱
# ==========================================
def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df.columns = [str(c).strip() for c in df.columns]

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
    df = df.loc[:, ~df.columns.duplicated()]

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

    df = df[required_cols].copy()

    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    if (
        pd.api.types.is_datetime64tz_dtype(df["datetime"])
        or df["datetime"].dt.tz is not None
    ):
        df["datetime"] = df["datetime"].dt.tz_localize(None)

    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["rainfall"] = pd.to_numeric(df["rainfall"], errors="coerce")

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
# 2. 獨立測站數據更新與寫入 (以 historical_data 為基礎進行合併)
# ==========================================
for s_id in target_stations:
    station_incoming = (
        new_df[new_df["station_id"] == s_id].copy()
        if not new_df.empty
        else pd.DataFrame()
    )

    # 1. 讀取歷史資料 (historical_data)
    history_matches = list(HISTORICAL_DIR.glob(f"{s_id}_*.csv"))
    historical_df = pd.DataFrame()
    if history_matches:
        for hist_file in history_matches:
            if hist_file.stat().st_size > 0:
                try:
                    raw_hdf = pd.read_csv(hist_file)
                    hdf = normalize_dataframe(raw_hdf)
                    historical_df = pd.concat([historical_df, hdf], ignore_index=True)
                except Exception as e:
                    print(f"讀取歷史檔案 {hist_file.name} 失敗: {e}")

    # 2. 讀取既有測站資料 (stations_data)
    station_matches = list(STATION_DIR.glob(f"{s_id}_*.csv"))
    exist_df = pd.DataFrame()
    if station_matches:
        for exist_file in station_matches:
            if exist_file.stat().st_size > 0:
                try:
                    raw_edf = pd.read_csv(exist_file)
                    edf = normalize_dataframe(raw_edf)
                    exist_df = pd.concat([exist_df, edf], ignore_index=True)
                except Exception as e:
                    print(f"讀取既有檔案 {exist_file.name} 失敗: {e}")

    # 合併三者：historical_data + stations_data + API新數據
    combined_station_df = pd.concat(
        [historical_df, exist_df, station_incoming], ignore_index=True
    )

    if combined_station_df.empty:
        continue

    combined_station_df["station_id"] = s_id
    
    # 清理重複項（若時間相同，保留最後出現者/最新數據）
    combined_station_df.drop_duplicates(
        subset=["station_id", "datetime"], keep="last", inplace=True
    )
    combined_station_df.sort_values(by="datetime", inplace=True)

    s_name = combined_station_df["station_name"].dropna().iloc[-1]
    
    # 格式化輸出
    output_df = combined_station_df.copy()
    output_df["datetime"] = output_df["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    station_csv_path = STATION_DIR / f"{s_id}_{s_name}.csv"
    output_df.to_csv(station_csv_path, index=False, encoding="utf-8-sig")

# ==========================================
# 3. 彙整歷史總表 (同時讀取 historical_data 與 stations_data)
# ==========================================
all_files = list(HISTORICAL_DIR.glob("*.csv")) + list(STATION_DIR.glob("*.csv"))
master_list = []

for f in all_files:
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
    master_df.drop_duplicates(subset=["station_id", "datetime"], keep="last", inplace=True)
    master_df.sort_values(by=["datetime", "station_id"], inplace=True)

    export_master_df = master_df.copy()
    export_master_df["datetime"] = export_master_df["datetime"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    export_master_df.to_csv(
        BASE_DIR / "weather_history.csv", index=False, encoding="utf-8-sig"
    )
    print(f"成功更新總表 weather_history.csv，共 {len(export_master_df)} 筆資料。")

# ==========================================
# 4. 繪製圖表 (修復雨量圖與柱狀圖寬度問題)
# ==========================================
# 1. 建立測站與顏色的對應字典 (可使用 HEX 色碼或 Matplotlib 顏色名稱)
    STATION_COLORS = {
        "C0TA40": "#FF5809",  # 橘紅色
        "C0TA50": "#A23400",  # 棕紅色
        "C0Z310": "#1F4E79",   # 深藍色
        "C0T9D0": "#5B9BD5",   # 藍色
        "C0Z220": "#70AD47",   # 綠色
        "C0Z230": "#DEEBF7"   # 淺藍色
    }

    # 【上圖】氣溫折線圖
    for label in station_labels:
        s_id = label.split()[0]  # 取得測站 ID (例如 C0TA40)
        group = plot_df[plot_df["StationLabel"] == label].dropna(subset=["temperature"])
        if group.empty:
            continue
        
        # 指定 color 參數
        ax1.plot(
            group["datetime"],
            group["temperature"],
            marker="o",
            markersize=1.5,
            linewidth=1,
            label=label,
            color=STATION_COLORS.get(s_id, "#333333")  # 若無設定則預設灰色
        )

    # 【下圖】雨量直條圖
    for label in station_labels:
        s_id = label.split()[0]
        group = plot_df[plot_df["StationLabel"] == label].dropna(subset=["rainfall"])
        if group.empty:
            continue

        rain_positive = group[group["rainfall"] > 0]

        if not rain_positive.empty:
            ax2.bar(
                rain_positive["datetime"],
                rain_positive["rainfall"],
                width=dynamic_bar_width,
                alpha=0.6,
                label=label,
                color=STATION_COLORS.get(s_id, "#333333")  # 使用相同測站顏色
            )
        else:
            ax2.plot(
                group["datetime"].iloc[:1],
                group["rainfall"].iloc[:1],
                alpha=0,
                label=label,
                color=STATION_COLORS.get(s_id, "#333333")
            )
if not master_df.empty:
    plot_df = master_df.copy()
    plot_df["StationLabel"] = (
        plot_df["station_id"] + " " + plot_df["station_name"]
    )
    plot_df.sort_values(by="datetime", inplace=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    station_labels = plot_df["StationLabel"].unique()

    # 計算全域時間跨度以設定合理的直條圖寬度 (預設寬度為總天數的 0.5%)
    total_days = (
        plot_df["datetime"].max() - plot_df["datetime"].min()
    ).total_seconds() / 86400
    dynamic_bar_width = max(total_days * 0.003, 0.5)  # 最少 0.5 天寬度避免消失

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
            markersize=1.5,
            linewidth=1,
            label=label,
        )

    t_title = ax1.set_title("即時氣溫變化圖 (°C)", fontsize=14, fontweight="bold")
    t_ylabel = ax1.set_ylabel("氣溫 (°C)", fontsize=12)
    ax1.grid(True, linestyle="--", alpha=0.5)
    leg1 = ax1.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # 【下圖】雨量直條圖 / 折線圖 (修復雨量無法顯示問題)
    for label in station_labels:
        group = plot_df[plot_df["StationLabel"] == label].dropna(
            subset=["rainfall"]
        )
        if group.empty:
            continue

        # 過濾出有雨量數據 (>0) 來畫顯著柱狀圖，避免 0mm 佔滿圖表
        rain_positive = group[group["rainfall"] > 0]

        if not rain_positive.empty:
            ax2.bar(
                rain_positive["datetime"],
                rain_positive["rainfall"],
                width=dynamic_bar_width,
                alpha=0.6,
                label=label,
            )
        else:
            # 若無降雨，畫一條隱形點維持 Legend
            ax2.plot(
                group["datetime"].iloc[:1],
                group["rainfall"].iloc[:1],
                alpha=0,
                label=label,
            )

    r_title = ax2.set_title("即時雨量直條圖 (mm)", fontsize=14, fontweight="bold")
    r_xlabel = ax2.set_xlabel("時間 (DateTime)", fontsize=12)
    r_ylabel = ax2.set_ylabel("雨量 (mm)", fontsize=12)
    ax2.grid(True, linestyle="--", alpha=0.5)
    leg2 = ax2.legend(loc="upper left", bbox_to_anchor=(1, 1))

    # 自動調整雨量 Y 軸上限，避免雨量極小導致沒反應
    max_rain = plot_df["rainfall"].max()
    if pd.notna(max_rain) and max_rain > 0:
        ax2.set_ylim(0, max_rain * 1.1)
    else:
        ax2.set_ylim(0, 10)  # 預設上限

    # X 軸時間軸格式設定
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=45)

    # 顯式指定中文 Properties
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
