weather-monitor/
├── .github/
│   └── workflows/
│       └── auto_run.yml             # 定時自動執行設定檔
│
├── config/                          # 靜態資源與設定檔
│   └── NotoSansCJKtc-Regular.otf    # 中文字型檔
│
├── src/                             # 所有 Python 程式碼 (模組化)
│   ├── app_dash.py                  # Dash 互動看板應用
│   ├── data_loader.py               # 資料處理與載入邏輯
│   └── main.py                      # 氣象資料抓取與繪圖主要流程
│
├── README.md                        # 專案說明文件
├── requirements.txt                 # Python 套件依賴清單
│
│  
├── weather_chart.png                # 產出的氣象視覺化圖表
├── stations_data.csv
│
├── historical_data/                 # 歷史天氣資料 (手動補齊資料)
│   ├── C0TA40_秀林.csv
│   ├── C0TA50_和仁.csv
│   ├── C0Z310_清水斷崖.csv
│   ├── C0T9D0_和中.csv
│   ├── C0Z220_和平林道.csv
│   └── C0Z230_和平.csv
│
└── stations_data/                   # 測站即時資料 (即時資料 + 歷史資料累積)
    ├── C0TA40_秀林.csv
    ├── C0TA50_和仁.csv
    ├── C0Z310_清水斷崖.csv
    ├── C0T9D0_和中.csv
    ├── C0Z220_和平林道.csv
    └── C0Z230_和平.csv
