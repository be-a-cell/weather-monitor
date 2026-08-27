from datetime import datetime, timedelta
from pathlib import Path
import time
import requests

# 1. 設定下載目標測站清單
STATIONS = {
    "C0TA40": "秀林",
    "C0TA50": "和仁",
    "C0Z310": "清水斷崖",
    "C0T9D0": "和中",
    "C0Z220": "和平林道",
    "C0Z230": "和平",
}

# 2. 設定日期區間
START_DATE = datetime(2022, 1, 1)
END_DATE = datetime.now()

# 儲存目錄 (raw/)
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def download_codis_data():
    # CODIS 下載 CSV 的底層 API URL
    url = "https://codis.cwa.gov.tw/api/station/day/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://codis.cwa.gov.tw/StationData",
    }

    current_date = START_DATE
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y-%m-%d")

        for st_id, st_name in STATIONS.items():
            # 檔名格式統一：C0Z230-2022-01-01.csv
            file_name = f"{st_id}-{date_str}.csv"
            save_path = RAW_DIR / file_name

            # 如果檔案已經下載過，自動跳過
            if save_path.exists():
                continue

            # API 請求參數
            params = {
                "stn_id": st_id,
                "start": f"{date_str}T00:00:00",
                "type": "csv",
            }

            try:
                response = requests.get(
                    url, headers=headers, params=params, timeout=10
                )
                if response.status_code == 200 and len(response.content) > 100:
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                    print(
                        f" Successfully downloaded: {st_id} ({st_name}) {date_str}"
                    )
                else:
                    print(
                        f" Failed or no data: {st_id} {date_str} (Status: {response.status_code})"
                    )
            except Exception as e:
                print(f" Error fetching {st_id} on {date_str}: {e}")

            # 禮貌防護：每次請求間隔 0.2 秒，避免伺服器防爬封鎖
            time.sleep(0.2)

        current_date += timedelta(days=1)


if __name__ == "__main__":
    print(
        f"開始自動爬取 CODIS 歷史資料 (區間: 2022-01-01 ~ {END_DATE.strftime('%Y-%m-%d')})..."
    )
    download_codis_data()
    print("所有歷史資料爬取完成！直接放在 raw/ 資料夾下。")
