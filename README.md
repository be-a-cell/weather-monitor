weather-crawler/
├── .github/
│   └── workflows/
│       └── run_weather.yml    # GitHub Actions 自動化腳本
├── config/
│   └── NotoSansCJKtc-Regular.otf  # 中文字型檔 (選填)
├── src/
│   ├── main.py                # 主要執行檔 (整合 Playwright + 圖表繪製 + SQLite)
│   └── weather_database.db    # SQLite 資料庫 (單一檔案，極省空間)
├── weather_chart.png          # 自動生成的最新趨勢圖
└── requirements.txt           # Python 依賴套件
