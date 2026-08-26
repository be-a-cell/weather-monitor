import json
import os
import pandas as pd

CONFIG_FILE = 'user_settings.json'


# 1. 記憶設定讀取與儲存
def load_settings():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'station': '福山',
        'start_date': '2022-01-01',
        'end_date': '2024-12-31',
        'temp_color': '#EF553B',
        'rain_color': '#636EFA',
    }


def save_settings(settings):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


# 2. 自動合併歷史與新資料
def load_all_weather_data():
    all_dfs = []
    hist_dir = 'historical_data'

    if os.path.exists(hist_dir):
        for file in os.listdir(hist_dir):
            if file.endswith('.csv'):
                file_path = os.path.join(hist_dir, file)
                try:
                    df = pd.read_csv(file_path)
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    all_dfs.append(df)
                except Exception as e:
                    print(f'讀取舊資料 {file} 失敗: {e}')

    if not all_dfs:
        return pd.DataFrame()

    df_combined = pd.concat(all_dfs, ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset=['station_id', 'datetime'])
    return df_combined.sort_values(by='datetime')
