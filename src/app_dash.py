import sys
from pathlib import Path
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objects as go
import plotly.subplots as sp

# ==========================================
# 0. 路徑修正 (確保能正確引用同目錄的 data_loader)
# ==========================================
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from data_loader import load_all_weather_data, load_settings, save_settings

# 載入預設設定與資料
saved_config = load_settings()
df = load_all_weather_data()

app = Dash(__name__)

# 取得可用測站清單
stations = df['station_name'].dropna().unique().tolist() if not df.empty and 'station_name' in df.columns else []
default_station = saved_config.get('station') if saved_config.get('station') in stations else (stations[0] if stations else None)

app.layout = html.Div([
    html.H2("氣象數據高級監控與出圖系統", style={'textAlign': 'center', 'marginBottom': '20px'}),
    
    # 控制面板
    html.Div([
        html.Div([
            html.Label("選擇站位：", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='station-picker',
                options=[{'label': s, 'value': s} for s in stations],
                value=default_station,
                placeholder="請選擇氣象測站"
            ),
        ], style={'width': '25%', 'display': 'inline-block', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("氣溫線顏色：", style={'fontWeight': 'bold'}),
            html.Br(),
            dcc.Input(id='temp-color', type='color', value=saved_config.get('temp_color', '#EF553B'), style={'height': '35px', 'width': '60px'}),
        ], style={'display': 'inline-block', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("雨量條顏色：", style={'fontWeight': 'bold'}),
            html.Br(),
            dcc.Input(id='rain-color', type='color', value=saved_config.get('rain_color', '#636EFA'), style={'height': '35px', 'width': '60px'}),
        ], style={'display': 'inline-block', 'marginRight': '20px'}),
        
        html.Div([
            html.Br(),
            html.Button('💾 記憶當前設定', id='save-btn', n_clicks=0, style={'padding': '8px 15px', 'marginRight': '10px', 'cursor': 'pointer'}),
            html.Button('🔄 重新讀取資料', id='reload-btn', n_clicks=0, style={'padding': '8px 15px', 'cursor': 'pointer'}),
        ], style={'display': 'inline-block'}),
        
        html.Div(id='save-status', style={'color': 'green', 'marginTop': '10px', 'fontWeight': 'bold'})
    ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px', 'marginBottom': '20px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}),
    
    # 圖表區域 (支援下載高解析度 PNG)
    dcc.Graph(
        id='weather-chart',
        config={
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'weather_export',
                'height': 800,
                'width': 1200,
                'scale': 2
            }
        }
    )
], style={'padding': '30px', 'fontFamily': 'Arial, sans-serif'})

# 更新圖表的回調函式
@app.callback(
    Output('weather-chart', 'figure'),
    Input('station-picker', 'value'),
    Input('temp-color', 'value'),
    Input('rain-color', 'value'),
    Input('reload-btn', 'n_clicks')
)
def update_graph(selected_station, temp_color, rain_color, reload_clicks):
    global df
    # 如果點擊重新讀取資料按鈕，重新載入 CSV
    if reload_clicks > 0:
        df = load_all_weather_data()

    if df.empty or not selected_station:
        fig = sp.make_subplots()
        fig.update_layout(title_text="暫無氣象資料，請確認資料夾內是否有 CSV 檔案", template="plotly_white")
        return fig

    filtered_df = df[df['station_name'] == selected_station].copy()

    # 建立雙 Y 軸圖表
    fig = sp.make_subplots(specs=[[{"secondary_y": True}]])
    
    # 氣溫折線
    if 'temperature' in filtered_df.columns:
        fig.add_trace(
            go.Scatter(
                x=filtered_df['datetime'],
                y=filtered_df['temperature'],
                name="氣溫 (°C)",
                line=dict(color=temp_color, width=2),
                connectgaps=True
            ),
            secondary_y=False
        )
    
    # 雨量柱狀圖
    if 'rainfall' in filtered_df.columns:
        fig.add_trace(
            go.Bar(
                x=filtered_df['datetime'],
                y=filtered_df['rainfall'],
                name="雨量 (mm)",
                marker_color=rain_color,
                opacity=0.6
            ),
            secondary_y=True
        )
    
    fig.update_layout(
        title_text=f"{selected_station} 歷年氣溫與雨量趨勢圖",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="氣溫 (°C)", secondary_y=False)
    fig.update_yaxes(title_text="雨量 (mm)", secondary_y=True)
    
    return fig

# 儲存使用者設定的回調函式
@app.callback(
    Output('save-status', 'children'),
    Input('save-btn', 'n_clicks'),
    State('station-picker', 'value'),
    State('temp-color', 'value'),
    State('rain-color', 'value')
)
def save_user_config(n_clicks, station, temp_color, rain_color):
    if n_clicks > 0:
        config = {
            'station': station,
            'temp_color': temp_color,
            'rain_color': rain_color
        }
        save_settings(config)
        return "✓ 設定已永久記憶至 config/user_settings.json！"
    return ""

if __name__ == '__main__':
    app.run(debug=True, port=8050)
