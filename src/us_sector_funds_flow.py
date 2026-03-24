import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import datetime
import os

# Configuration
tickers = ['XLK', 'XLV', 'XLF', 'XLY', 'XLP', 'XLE', 'XLI', 'XLB', 'XLU', 'XLRE', 'XLC']
benchmark = 'SPY'
all_tickers = tickers + [benchmark]

# Map ETF tickers to Chinese sector names
sector_map = {
    'XLK': '科技 (XLK)',
    'XLV': '醫療保健 (XLV)',
    'XLF': '金融 (XLF)',
    'XLY': '非必需消費 (XLY)',
    'XLP': '必需消費 (XLP)',
    'XLE': '能源 (XLE)',
    'XLI': '工業 (XLI)',
    'XLB': '原物料 (XLB)',
    'XLU': '公用事業 (XLU)',
    'XLRE': '房地產 (XLRE)',
    'XLC': '通訊服務 (XLC)'
}

# Fetch data for the maximum period needed
print("Fetching 10 years of data from yfinance...")
data = yf.download(all_tickers, period="10y")

# Handle MultiIndex for latest yfinance versions
if isinstance(data.columns, pd.MultiIndex):
    if 'Adj Close' in data.columns.levels[0]:
        data = data['Adj Close']
    elif 'Close' in data.columns.levels[0]:
        data = data['Close']
else:
    if 'Adj Close' in data.columns:
        data = data['Adj Close']
    else:
        data = data['Close']

# Drop rows with all NaN and handle missing
data.dropna(how='all', inplace=True)
data.ffill(inplace=True)
data.dropna(inplace=True)

# Function to generate charts for a specific timeframe
def generate_charts_for_period(df_subset, period_label):
    if df_subset.empty or len(df_subset) < 2:
        return None, None, None, None

    # Calculate Cumulative Return (%)
    cum_returns = (df_subset / df_subset.iloc[0] - 1) * 100

    # Calculate Relative Strength (Alpha) vs SPY
    relative_strength = cum_returns.copy()
    for ticker in tickers:
        relative_strength[ticker] = cum_returns[ticker] - cum_returns[benchmark]

    # Get the latest cumulative returns to find top 3
    latest_returns = cum_returns.iloc[-1].drop(benchmark)
    top_3_tickers = latest_returns.nlargest(3).index.tolist()

    # Get the latest relative strength for the bar chart
    latest_rs = relative_strength.iloc[-1].drop(benchmark).sort_values(ascending=True)

    # ----------------- Plot 1: Cumulative Returns Line Chart -----------------
    plt.figure(figsize=(12, 6))
    plt.style.use('ggplot')

    for col in cum_returns.columns:
        if col == benchmark:
            plt.plot(cum_returns.index, cum_returns[col], color='black', linestyle='--', linewidth=3.5, label=f'{col} (Benchmark)')
        elif col in top_3_tickers:
            plt.plot(cum_returns.index, cum_returns[col], linewidth=3, label=f'{col} (Top 3)')
        else:
            plt.plot(cum_returns.index, cum_returns[col], linewidth=1.5, alpha=0.5, label=col)

    plt.title(f'{period_label} Cumulative Return: US Sectors vs SPY', fontsize=16, fontweight='bold')
    plt.ylabel('Cumulative Return (%)', fontsize=12)
    plt.xlabel('Date', fontsize=12)
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5), fontsize=10)
    plt.tight_layout()

    buf1 = BytesIO()
    plt.savefig(buf1, format='png', bbox_inches='tight', dpi=120)
    buf1.seek(0)
    img1_base64 = base64.b64encode(buf1.read()).decode('utf-8')
    plt.close()

    # ----------------- Plot 2: Relative Strength Bar Chart -----------------
    plt.figure(figsize=(10, 6))
    colors = ['green' if x > 0 else 'red' for x in latest_rs]
    bars = plt.barh(latest_rs.index, latest_rs, color=colors)

    plt.title(f'{period_label} Relative Strength vs SPY (Latest)', fontsize=16, fontweight='bold')
    plt.xlabel('Alpha (%)', fontsize=12)
    plt.ylabel('Sector ETF', fontsize=12)
    plt.axvline(0, color='black', linewidth=1.5)

    for bar in bars:
        width = bar.get_width()
        label_x_pos = width + max(0.3, abs(width)*0.05) if width > 0 else width - max(0.3, abs(width)*0.05)
        ha = 'left' if width > 0 else 'right'
        plt.text(label_x_pos, bar.get_y() + bar.get_height()/2, f'{width:.2f}%', va='center', ha=ha, fontsize=10, fontweight='bold')

    plt.xlim(latest_rs.min() * 1.2, latest_rs.max() * 1.2)
    plt.tight_layout()

    buf2 = BytesIO()
    plt.savefig(buf2, format='png', bbox_inches='tight', dpi=120)
    buf2.seek(0)
    img2_base64 = base64.b64encode(buf2.read()).decode('utf-8')
    plt.close()
    
    return img1_base64, img2_base64, latest_rs, top_3_tickers


# Define timeframes
end_date = data.index[-1]
periods = [
    ('10Y', end_date - pd.DateOffset(years=10)),
    ('5Y', end_date - pd.DateOffset(years=5)),
    ('3Y', end_date - pd.DateOffset(years=3)),
    ('1Y', end_date - pd.DateOffset(years=1)),
    ('6M', end_date - pd.DateOffset(months=6))
]

charts_html_sections = []
interpretation_html = ""

for label, start_date in periods:
    print(f"Processing data for {label}...")
    # timezone awareness handling: ensure both are naive or both timezone aware
    if data.index.tz is not None and start_date.tzinfo is None:
        start_date = start_date.tz_localize(data.index.tz)
    elif data.index.tz is None and start_date.tzinfo is not None:
        start_date = start_date.tz_localize(None)
        
    df_subset = data.loc[start_date:]
    img1, img2, latest_rs, top_3 = generate_charts_for_period(df_subset, label)
    
    if not img1:
        print(f"Skipping {label} due to lack of data.")
        continue
        
    section_html = f"""
    <div class="timeframe-section">
        <h2 class="timeframe-title">時間維度：{label}</h2>
        <div class="charts-container">
            <div class="chart">
                <img src="data:image/png;base64,{img1}" alt="{label} Cumulative Returns">
            </div>
            <div class="chart">
                <img src="data:image/png;base64,{img2}" alt="{label} Relative Strength">
            </div>
        </div>
    </div>
    """
    charts_html_sections.append(section_html)
    
    # Only generate textual interpretation for the 6-month period
    if label == '6M':
        strong_sectors = latest_rs[latest_rs > 0].index.tolist()
        weak_sectors = latest_rs[latest_rs < 0].index.tolist()

        strong_sectors_cn = ", ".join([sector_map.get(s, s) for s in strong_sectors[::-1]])
        weak_sectors_cn = ", ".join([sector_map.get(s, s) for s in weak_sectors])
        top_3_cn = ", ".join([sector_map.get(s, s) for s in top_3])

        interpretation_html = f"""
        <div class="interpretation">
            <h3>近 6 個月市場資金流向趨勢解讀</h3>
            <ul>
                <li><b style="color: green;">短線資金流入 (跑贏大盤)：</b> 相對報酬 (Alpha) 大於零的板塊為 <b>{strong_sectors_cn if strong_sectors_cn else '無'}</b>。這代表近半年的資金青睞度較高，領先群包含 <b>{top_3_cn}</b>。</li>
                <li><b style="color: red;">短線資金流出 (跑輸大盤)：</b> 相對報酬 (Alpha) 小於零的板塊包含 <b>{weak_sectors_cn if weak_sectors_cn else '無'}</b>。顯示這些板塊近期動能較弱，短線面臨資金撤出或逆風。</li>
            </ul>
        </div>
        """

# Prepare the legend HTML
legend_items = [f"<span class='legend-item'><b>SPY</b>: 標普500大盤</span>"]
for tkr, nm in sector_map.items():
    clean_name = nm.split(" ")[0]
    legend_items.append(f"<span class='legend-item'><b>{tkr}</b>: {clean_name}</span>")

legend_html = f'''
        <div class="legend-box">
            <h3>板塊 ETF 代號對照表</h3>
            <div class="legend-grid">
                {''.join(legend_items)}
            </div>
        </div>
'''

# Combine HTML
html_content = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>美股 11 大板塊多時間維度分析 (10y/5y/3y/1y/6mo)</title>
    <style>
        body {{
            font-family: 'Microsoft JhengHei', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f0f4f8;
            color: #2c3e50;
        }}
        .header {{
            text-align: center;
            padding: 20px 0;
            background-color: #34495e;
            color: #ecf0f1;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .timeframe-section {{
            background-color: #ffffff;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            border-top: 5px solid #3498db;
        }}
        .timeframe-title {{
            color: #2980b9;
            text-align: left;
            font-size: 22px;
            margin-top: 0;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #ecf0f1;
        }}
        .charts-container {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            gap: 20px;
        }}
        .chart {{
            flex: 1 1 calc(50% - 20px);
            min-width: 500px;
            text-align: center;
        }}
        img {{
            width: 100%;
            height: auto;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
        }}
        @media (max-width: 1100px) {{
            .chart {{
                flex: 1 1 100%;
                min-width: 100%;
            }}
        }}
        .interpretation {{
            background-color: #fff8e1;
            padding: 20px;
            border-left: 6px solid #f39c12;
            border-radius: 6px;
            font-size: 16px;
            line-height: 1.6;
            margin-top: 10px;
        }}
        .interpretation h3 {{
            margin-top: 0;
            color: #d35400;
        }}
        .interpretation ul {{
            margin-bottom: 0;
            padding-left: 20px;
        }}
        .interpretation li {{
            margin-bottom: 10px;
        }}
        .legend-box {{
            background-color: #ffffff;
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 30px;
            border: 1px solid #dcdde1;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .legend-box h3 {{
            margin-top: 0;
            margin-bottom: 15px;
            color: #2c3e50;
            font-size: 18px;
            text-align: center;
        }}
        .legend-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            justify-content: center;
        }}
        .legend-item {{
            background-color: #f8f9fa;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 15px;
            border: 1px solid #e9ecef;
            color: #34495e;
        }}
        .legend-item b {{
            color: #e67e22;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>美股 11 大板塊趨勢與資金流向 (多維度觀測)</h1>
        </div>
        
        {legend_html}
        
        {''.join(charts_html_sections)}
        
        {interpretation_html}
    </div>
</body>
</html>
"""

# Create reports directory if it doesn't exist
reports_dir = os.path.join(os.getcwd(), "outputs", "reports")
os.makedirs(reports_dir, exist_ok=True)

# Generate timestamped filename
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"us_sector_funds_flow_{timestamp}.html"
html_file_path = os.path.join(reports_dir, filename)

# Write directly to HTML file
with open(html_file_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Analysis complete. Results generated in: {os.path.abspath(html_file_path)}")
