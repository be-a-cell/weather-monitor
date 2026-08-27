from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objects as scipy_go
import plotly.subplots as sp
from data_loader import load_all_weather_data, load_settings, save_settings

# 載入預設記憶與資料
saved_config = load_settings()
df = load_all_weather_data()

app = Dash(__name__)

stations = df['station_name'].unique().tolist() if not df.empty else []

app.layout = html.Div([
    html.H2("氣象數據高級監控與出圖系統"),
    
    # 控制面板
    html.Div([
        html.Div([
            html.Label("選擇站位："),
            dcc.Dropdown(id='station-picker', options=[{'label': s, 'value': s} for s in stations], value=saved_config.get('station')),
        ], style={'width': '20%', 'display': 'inline-block', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("氣溫線顏色："),
            dcc.Input(id='temp-color', type='color', value=saved_config.get('temp_color', '#EF553B')),
        ], style={'display': 'inline-block', 'marginRight': '20px'}),
        
        html.Div([
            html.Label("雨量條顏色："),
            dcc.Input(id='rain-color', type='color', value=saved_config.get('rain_color', '#636EFA')),
        ], style={'display': 'inline-block', 'marginRight': '20px'}),
        
        html.Button('💾 記憶當前設定', id='save-btn', n_clicks=0),
        html.Div(id='save-status', style={'color': 'green', 'marginTop': '5px'})
    ], style={'padding': '15px', 'backgroundColor': '#f9f9f9', 'marginBottom': '20px'}),
    
    # 圖表區域 (支援直接下載 PNG)
    dcc.Graph(id='weather-chart', config={'toImageButtonOptions': {'format': 'png', 'filename': 'weather_export', 'height': 800, 'width': 1200, 'scale': 2}})
])

@app.callback(
    Output('weather-chart', 'figure'),
    Input('station-picker', 'value'),
    Input('temp-color', 'value'),
    Input('rain-color', 'value')
)
def update_graph(selected_station, temp_color, rain_color):
    filtered_df = df[df['station_name'] == selected_station]
    
    # 建立雙 Y 軸圖表
    fig = sp.make_subplots(specs=[[{"secondary_y": True}]])
    
    # 氣溫折線
    fig.add_trace(
        scipy_go.Scatter(x=filtered_df['datetime'], y=filtered_df['temperature'], name="氣溫 (°C)", line=dict(color=temp_color, width=2)),
        secondary_y=False
    )
    
    # 雨量柱狀圖
    fig.add_trace(
        scipy_go.Bar(x=filtered_df['datetime'], y=filtered_df['rainfall'], name="雨量 (mm)", marker_color=rain_color, opacity=0.6),
        secondary_y=True
    )
    
    fig.update_layout(title_text=f"{selected_station} 歷年氣溫與雨量趨勢圖", template="plotly_white", hovermode="x unified")
    fig.update_yaxes(title_text="氣溫 (°C)", secondary_y=False)
    fig.update_yaxes(title_text="雨量 (mm)", secondary_y=True)
    
    return fig

# 點擊按鈕寫入 user_settings.json 記憶
@app.callback(
    Output('save-status', 'children'),
    Input('save-btn', 'n_clicks'),
    State('station-picker', 'value'),
    State('temp-color', 'value'),
    State('rain-color', 'value')
)
def save_user_config(n_clicks, station, temp_color, rain_color):
    if n_clicks > 0:
        config = {'station': station, 'temp_color': temp_color, 'rain_color': rain_color}
        save_settings(config)
        return "✓ 設定已永久記憶！下一次開啟時將自動載入此樣式。"
    return ""

if __name__ == '__main__':
    app.run_server(debug=True, port=8050)
