import glob
import os
import pandas as pd


def process_weather_data(input_dir="raw_data", output_file="cleaned_data.csv"):
    all_data = []

    for file_path in glob.glob(os.path.join(input_dir, "*.csv")):
        filename = os.path.basename(file_path)

        # 1. 自動從檔名提取測站與日期 (例: C0Z220-2026-08-26.csv)
        station_id, date_str = filename.replace(".csv", "").split("-", 1)

        # 2. 跳過第 0 行中文欄位，直接以第 1 行英文欄位作為欄位名
        df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")

        # 3. 補充 Metadata 欄位
        df.insert(0, "Station", station_id)
        df.insert(1, "Date", date_str)

        # 4. 校正時間格式：ObsTime 補零，並轉為標準 ISO 時間戳 (處理 24 時跨日問題)
        df["ObsTime"] = df["ObsTime"].astype(str).str.zfill(2)
        df["Datetime"] = pd.to_datetime(
            date_str + " " + df["ObsTime"].replace({"24": "00"}),
            format="%Y-%m-%d %H",
        )
        df.loc[df["ObsTime"] == "24", "Datetime"] += pd.Timedelta(days=1)

        # 5. 氣象特殊符號清洗 (例如雨量 'T' 轉 0.05，異常符號 '&' 或 '-' 轉 NaN)
        df["Precp"] = df["Precp"].replace({"T": 0.05, "x": None, "&": None})

        # 6. 強制轉為數值型態 (非數字會自動轉為 NaN)
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

        all_data.append(df)

    if all_data:
        merged_df = pd.concat(all_data, ignore_index=True)
        merged_df.sort_values(by=["Station", "Datetime"], inplace=True)
        merged_df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(
            f"成功合併 {len(all_data)} 個檔案，共 {len(merged_df)} 筆資料，輸出至 {output_file}"
        )


if __name__ == "__main__":
    process_weather_data()
