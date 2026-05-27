"""
US Liquidity Dashboard - 2026 White Paper Design
Professional FinTech Interface with Educational Components
"""
import os  # <--- 就是少了這一行！用來讀取系統環境變數
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import streamlit.components.v1 as components
from fed_data import fetch_fed_data, analyze_market_dynamics, get_sparkline_data, calculate_delta, generate_ai_summary

# === DESIGN SYSTEM ===
COLORS = {
    "canvas": "#FFFFFF", "ink": "#0F172A", "federal_blue": "#0044CC",    
    "tech_silver": "#E2E8F0", "emerald": "#10B981", "red": "#EF4444", "amber": "#F59E0B",           
}
MILLIONS_TO_TRILLION = 1e6

st.set_page_config(page_title="US Liquidity Dashboard", page_icon="🏦", layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""
<style>
    .stApp {{ background-color: {COLORS['canvas']}; }}
    * {{ font-family: 'Inter', 'Roboto', -apple-system, sans-serif; color: {COLORS['ink']}; }}
    .block-container {{ padding-top: 2rem; padding-bottom: 2rem; max-width: 1400px; }}
    div[data-testid="stMetric"] {{
        background-color: {COLORS['canvas']}; border: 1px solid {COLORS['tech_silver']};
        padding: 1rem; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }}
    h1, h2, h3 {{ color: {COLORS['federal_blue']}; font-weight: 700; }}
    hr {{ border-color: {COLORS['tech_silver']}; margin: 2rem 0; }}
    .health-score-container {{
        display: flex; align-items: center; padding: 1.5rem;
        border: 1px solid {COLORS['tech_silver']}; border-radius: 8px; margin-bottom: 2rem;
    }}
    .health-score-circle {{
        font-size: 3rem; font-weight: 800; padding: 1rem 2rem;
        border-radius: 50%; color: white; margin-right: 2rem;
    }}
    .explanation-box {{
        background-color: #F8FAFC; border-left: 4px solid {COLORS['federal_blue']};
        padding: 1rem; border-radius: 0 4px 4px 0; font-size: 0.95rem; margin-top: 0.5rem;
    }}
    
    /* === 列印成 PDF 專用的排版 === */
    @media print {{
        /* 強制橫向列印，並設定邊距 */
        @page {{
            size: landscape;
            margin: 10mm;
        }}
        
        header[data-testid="stHeader"] {{ display: none !important; }}
        section[data-testid="stSidebar"] {{ display: none !important; }}
        
        /* 確保背景維持乾淨的白色 */
        .stApp, body {{ background-color: #FFFFFF !important; }}
        
        /* 強制展開主容器，不要留太多白邊 */
        .block-container {{ 
            padding: 0rem !important; 
            max-width: 100% !important; 
            width: 100% !important;
        }}
        
        /* 確保 Streamlit 的欄位 (columns) 在列印時能維持並排，不會被折疊成單行 */
        div[data-testid="column"] {{
            flex: 1 1 0% !important;
            min-width: 0 !important;
        }}

        /* 避免圖表和解說框被切斷在兩頁之間 */
        .js-plotly-plot {{ page-break-inside: avoid; }}
        .health-score-container, .explanation-box {{ page-break-inside: avoid; }}
    }}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def load_data(): 
    return fetch_fed_data()

def to_trillion(val): 
    return val / MILLIONS_TO_TRILLION

def render_health_score(market_analysis: dict):
    if not market_analysis or 'macro_health' not in market_analysis: return
    health = market_analysis['macro_health']
    bg_color = COLORS['emerald'] if health['score'] >= 80 else (COLORS['amber'] if health['score'] >= 50 else COLORS['red'])
    
    st.markdown(f"""
    <div class="health-score-container">
        <div class="health-score-circle" style="background-color: {bg_color};">{health['score']}</div>
        <div>
            <h2 style="margin:0; color:{COLORS['ink']};">整體資金健康度 (Macro Health Score)</h2>
            <h4 style="margin: 5px 0; color: {bg_color};">{health['status']}</h4>
            <p style="margin:0; color:#64748B;">{health['description']}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_ai_broadcast(df):
    st.subheader("🎙️ AI 總經教授的晨間廣播")
    
    # === 防呆機制：安全地讀取 API Key ===
    api_key = None
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.info("💡 尚未偵測到 Gemini API Key。請在 `.streamlit/secrets.toml` 中設定 `GEMINI_API_KEY` 以解鎖 AI 自動解盤功能！")
        return

    # === 重點更新：改用 ai_data 接收 JSON 字典 ===
    if "ai_data" not in st.session_state:
        with st.spinner("正在連線到 AI 大腦，幫你深度解讀市場..."):
            try:
                st.session_state.ai_data = generate_ai_summary(df, api_key)
            except Exception as e:
                st.session_state.ai_data = {"error": f"AI 暫時無法連線，請檢查網路或 API Key 是否正確。({str(e)})"}
    
    # 解析 JSON 字典中的 broadcast 內容
    if "error" in st.session_state.ai_data:
        broadcast_text = st.session_state.ai_data["error"]
    else:
        broadcast_text = st.session_state.ai_data.get("broadcast", "無法生成廣播。")

    st.markdown(f"""
    <div style="background-color: #F8FAFC; border: 1px solid {COLORS['tech_silver']}; border-left: 4px solid {COLORS['federal_blue']}; padding: 20px; border-radius: 4px; margin-bottom: 20px;">
        <div style="font-size: 1.05rem; line-height: 1.7; color: {COLORS['ink']};">
            {broadcast_text}
        </div>
        <div style="text-align: right; margin-top: 15px; font-size: 0.8rem; color: #64748B;">
            🤖 Generated by Google Gemini Flash
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("🔄 重新請 AI 解讀"):
        if "ai_data" in st.session_state:
            del st.session_state.ai_data
        # 把舊的快取也清掉以防萬一
        if "ai_summary" in st.session_state:
            del st.session_state.ai_summary
        st.rerun()

def render_water_tanks(latest: pd.Series):
    st.subheader("💧 聯準會資金流向：三大水箱與警戒水位")
    st.markdown("相對於流動，我們更需要關注**「庫存容量」**。淺色長條代表水箱的歷史最大容量，實心顏色是目前的實際水位，🔴 **紅虛線**則是市場公認的「安全警戒線」。")
    
    reserves = to_trillion(latest.get("Reserve_Balances", 0))
    on_rrp = to_trillion(latest.get("ON_RRP", 0))
    tga = to_trillion(latest.get("TGA_Account", 0))

    safe_levels = [3.0, 0.2, 0.75]
    max_capacities = [4.5, 2.5, 1.5]  
    categories = ["🏦 準備金水箱<br>(銀行活水)", "🅿️ ON RRP 水箱<br>(備用緩衝)", "🏛️ TGA 水箱<br>(政府錢包)"]
    current_levels = [reserves, on_rrp, tga]
    colors = [COLORS['emerald'], COLORS['amber'], COLORS['federal_blue']]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=categories, y=max_capacities, name="水箱總容量", marker_color=COLORS['tech_silver'], opacity=0.3, hoverinfo='skip'))
    fig.add_trace(go.Bar(
        x=categories, y=current_levels, name="目前水位", marker_color=colors,
        text=[f"{v:.2f}T" for v in current_levels], textposition='outside',
        textfont=dict(color=COLORS['ink'], size=20, weight='bold')
    ))
    for i, target in enumerate(safe_levels):
        fig.add_shape(type="line", x0=i - 0.4, x1=i + 0.4, y0=target, y1=target, line=dict(color=COLORS['red'], width=3, dash="dash"))
        fig.add_annotation(x=i, y=target + 0.15, text=f"安全線: {target}T", showarrow=False, font=dict(color=COLORS['red'], size=12))

    fig.update_layout(
        barmode='overlay', height=450, paper_bgcolor=COLORS['canvas'], plot_bgcolor=COLORS['canvas'], font=dict(color=COLORS['ink']),
        yaxis=dict(title="Trillions USD (兆美元)", showgrid=True, gridcolor=COLORS['tech_silver'], tickfont=dict(color=COLORS['ink'], size=12)),
        xaxis=dict(showgrid=False, tickfont=dict(color=COLORS['ink'], size=14)), showlegend=False, margin=dict(t=50, b=10)
    )
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='explanation-box'><b>🏦 準備金 ({reserves:.2f}T)</b><br>水位越高，銀行越敢借錢。跌破 3.0T 市場會恐慌。</div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='explanation-box'><b>🅿️ 逆回購 ({on_rrp:.2f}T)</b><br>資金的停車場。跌破 0.2T 代表備用金乾涸。</div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='explanation-box'><b>🏛️ 財政部 ({tga:.2f}T)</b><br>政府錢包。變滿代表把市場的錢抽走了；花錢時水會流回市場。</div>", unsafe_allow_html=True)

def render_interest_rates(df: pd.DataFrame):
    st.subheader("📊 關鍵利率指標 (Interest Rates Demystified)")
    st.markdown("看懂這幾個利率，你就看懂了華爾街銀行間的「搶錢大戰」與「對未來景氣的預期」。")
    if "ai_data" in st.session_state and "rates_insight" in st.session_state.ai_data:
        st.info(f"🤖 **AI 利率快評：** {st.session_state.ai_data['rates_insight']}")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    def get_delta_str(delta, prev):
        if delta is None or prev is None: return None
        return f"{delta:+.3f}% (前日: {prev:.3f}%)"

    with col1:
        val, prev, delta, _ = calculate_delta(df, "SOFR")
        st.metric("SOFR (市場融資)", f"{val:.3f}%" if val else "—", get_delta_str(delta, prev))
        insight = "資金成本穩定，市場運作正常。"
        if delta is not None:
            if delta >= 0.01: insight = "🔴 短期借款變貴，市場在搶現金。"
            elif delta <= -0.01: insight = "🟢 資金轉趨寬鬆，借錢成本下降。"
        st.markdown(f"<div class='explanation-box'><b>🏢 短期借錢真實成本</b><br><span style='font-size: 0.85em; color: #475569;'>華爾街拿公債抵押借錢一晚的利息。</span><hr style='margin: 8px 0; border-color: {COLORS['tech_silver']};'><span style='font-size: 0.85em; color: {COLORS['federal_blue']};'><b>💡 洞見：</b>{insight}</span></div>", unsafe_allow_html=True)

    with col2:
        val, prev, delta, _ = calculate_delta(df, "IORB")
        st.metric("IORB (Fed 地板價)", f"{val:.3f}%" if val else "—", get_delta_str(delta, prev))
        insight = "聯準會按兵不動，政策維持現狀。"
        if delta is not None:
            if delta > 0: insight = "🔴 聯準會剛升息！收緊市場資金。"
            elif delta < 0: insight = "🟢 聯準會剛降息！釋放資金活水。"
        st.markdown(f"<div class='explanation-box'><b>🛡️ 聯準會無風險利息</b><br><span style='font-size: 0.85em; color: #475569;'>銀行乖乖存錢在聯準會拿的利息，是市場地板價。</span><hr style='margin: 8px 0; border-color: {COLORS['tech_silver']};'><span style='font-size: 0.85em; color: {COLORS['federal_blue']};'><b>💡 洞見：</b>{insight}</span></div>", unsafe_allow_html=True)

    with col3:
        val, prev, delta, _ = calculate_delta(df, "EFFR")
        st.metric("EFFR (銀行周轉)", f"{val:.3f}%" if val else "—", get_delta_str(delta, prev))
        insight = "銀行間流動性平穩充裕。"
        if delta is not None:
            if delta >= 0.02: insight = "⚠️ 銀行間周轉稍微吃緊。"
            elif delta <= -0.02: insight = "🟢 銀行間周轉資金寬鬆。"
        st.markdown(f"<div class='explanation-box'><b>🤝 銀行間的過夜利息</b><br><span style='font-size: 0.85em; color: #475569;'>銀行為滿足法規準備金互相借錢的利率。</span><hr style='margin: 8px 0; border-color: {COLORS['tech_silver']};'><span style='font-size: 0.85em; color: {COLORS['federal_blue']};'><b>💡 洞見：</b>{insight}</span></div>", unsafe_allow_html=True)

    with col4:
        val, prev, delta, _ = calculate_delta(df, "DGS2")
        st.metric("DGS2 (2年期公債)", f"{val:.3f}%" if val else "—", get_delta_str(delta, prev))
        insight = "近期貨幣政策預期無太大變動。"
        if delta is not None:
            if delta >= 0.03: insight = "🔴 市場預期降息延後，或有升息可能。"
            elif delta <= -0.03: insight = "🟢 市場強烈預期未來準備降息。"
        st.markdown(f"<div class='explanation-box'><b>🏃 短期經濟溫度計</b><br><span style='font-size: 0.85em; color: #475569;'>高度反映聯準會近期的升降息政策預期。</span><hr style='margin: 8px 0; border-color: {COLORS['tech_silver']};'><span style='font-size: 0.85em; color: {COLORS['federal_blue']};'><b>💡 洞見：</b>{insight}</span></div>", unsafe_allow_html=True)

    with col5:
        val, prev, delta, _ = calculate_delta(df, "DGS10")
        st.metric("DGS10 (10年公債)", f"{val:.3f}%" if val else "—", get_delta_str(delta, prev))
        insight = "長期經濟與通膨預期穩定。"
        if delta is not None:
            if delta >= 0.03: insight = "🔴 通膨預期升溫，不利科技股與房貸族。"
            elif delta <= -0.03: insight = "🟢 經濟預期放緩，有利債市與成長股。"
        st.markdown(f"<div class='explanation-box'><b>⚓ 長期經濟定價錨</b><br><span style='font-size: 0.85em; color: #475569;'>反映未來十年通膨與增長預期，決定房貸利率。</span><hr style='margin: 8px 0; border-color: {COLORS['tech_silver']};'><span style='font-size: 0.85em; color: {COLORS['federal_blue']};'><b>💡 洞見：</b>{insight}</span></div>", unsafe_allow_html=True)

def render_market_insights(market_analysis: dict):
    st.subheader("💡 AI 資金與經濟動態解析 (Macro Dynamics)")
    
    # === 新增的 AI 點評與防呆機制 ===
    if "ai_data" in st.session_state:
        if "macro_insight" in st.session_state.ai_data:
            st.info(f"🤖 **AI 資金流動性快評：** {st.session_state.ai_data['macro_insight']}")
        elif "error" in st.session_state.ai_data:
            st.warning(f"⚠️ AI 發生錯誤：{st.session_state.ai_data['error']}")
    else:
        # 如果走到這裡，代表最上方的廣播區塊沒有成功存入 ai_data
        pass 
    # ==============================

    cols = st.columns(4)
    keys = ['liquidity_stress', 'buffer_depletion', 'qt_intensity', 'yield_curve']
    for idx, key in enumerate(keys):
        with cols[idx]:
            if key in market_analysis and market_analysis[key]:
                data = market_analysis[key]
                st.markdown(f"""
                <div style="border: 1px solid {COLORS['tech_silver']}; padding: 1.5rem; border-radius: 8px; border-top: 4px solid {data['color']}; height: 100%;">
                    <strong style="color: {data['color']}; font-size: 1.1rem;">{data['label']}</strong><br>
                    <div style="margin-top: 10px; font-weight: 600; font-size: 0.95rem;">📊 專業數據：</div>
                    <div style="font-size: 0.9rem; color: #475569; margin-bottom: 10px;">{data['insight']}</div>
                    <div style="margin-top: 10px; font-weight: 600; font-size: 0.95rem;">🎓 白話翻譯：</div>
                    <div style="font-size: 0.95rem; color: {COLORS['federal_blue']}; background-color: #F0F4FA; padding: 10px; border-radius: 4px;">{data['layman_explanation']}</div>
                </div>
                """, unsafe_allow_html=True)

def render_sparklines(df: pd.DataFrame):
    st.subheader("📈 歷史位階與趨勢判定 (Historical Context - 10 Years)")
    st.markdown("單看今天的數字沒感覺。我們拉長到 **10 年 (2016-2026)**，看看經歷過疫情無限 QE 後，現在的資金水位到底在哪裡。")

    cols = st.columns(3)
    indicators = [
        {
            "col": "Reserve_Balances", "label": "🏦 準備金 (銀行底氣)", "color": COLORS['emerald'],
            "danger_zone": 3.0, "safe_zone": 3.2, "desc_up": "銀行手骨越來越粗。", "desc_down": "銀行正在失血。"
        },
        {
            "col": "ON_RRP", "label": "🅿️ ON RRP (備用緩衝)", "color": COLORS['amber'],
            "danger_zone": 0.2, "safe_zone": 1.0, "desc_up": "備用資金增加。", "desc_down": "市場正在吃老本！"
        },
        {
            "col": "TGA_Account", "label": "🏛️ TGA (政府金庫)", "color": COLORS['federal_blue'],
            "danger_zone": 0.2, "safe_zone": 0.75, "desc_up": "政府正在抽血存錢。", "desc_down": "政府花錢，資金流入民間。"
        }
    ]

    for idx, conf in enumerate(indicators):
        with cols[idx]:
            col_name = conf["col"]
            sparkline_data = get_sparkline_data(df, col_name, periods=3650) 
            if sparkline_data.empty: continue
            
            sparkline_data[col_name] = to_trillion(sparkline_data[col_name])
            current_val = sparkline_data[col_name].iloc[-1]
            hist_max, hist_min = sparkline_data[col_name].max(), sparkline_data[col_name].min()
            pr_value = int(((current_val - hist_min) / (hist_max - hist_min)) * 100) if hist_max > hist_min else 50
            
            month_ago_val = sparkline_data[col_name].iloc[-30]
            is_trending_up = current_val > month_ago_val
            trend_icon = "↗️ 上升中" if is_trending_up else "↘️ 下降中"
            trend_text = conf["desc_up"] if is_trending_up else conf["desc_down"]

            fig = go.Figure()
            fig.add_hrect(y0=0, y1=conf["danger_zone"], fillcolor=COLORS['red'], opacity=0.08, line_width=0, layer="below")
            fig.add_hrect(y0=conf["safe_zone"], y1=hist_max * 1.1, fillcolor=COLORS['emerald'], opacity=0.08, line_width=0, layer="below")
            fig.add_trace(go.Scatter(x=sparkline_data.index, y=sparkline_data[col_name], mode='lines', line=dict(color=conf["color"], width=2), hovertemplate='%{x|%Y-%m-%d}<br>%{y:.2f}T<extra></extra>'))

            fig.update_layout(
                title={'text': conf["label"], 'font': {'size': 16, 'color': COLORS['ink'], 'weight': 'bold'}, 'x': 0.5},
                height=250, showlegend=False, paper_bgcolor=COLORS['canvas'], plot_bgcolor=COLORS['canvas'], font=dict(color=COLORS['ink']),
                xaxis=dict(visible=True, showgrid=False, tickformat="%y", tickprefix="Y", tickfont=dict(color=COLORS['ink'], size=12)), 
                yaxis=dict(visible=True, showgrid=False, tickfont=dict(color=COLORS['ink'], size=11)), 
                margin=dict(l=30, r=20, t=40, b=30)
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(f"""
            <div style="background-color: #F8FAFC; border: 1px solid {COLORS['tech_silver']}; padding: 12px; border-radius: 6px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-size: 0.9rem; font-weight: 600; color: {COLORS['ink']};">10 年相對位階：</span>
                    <span style="font-size: 0.9rem; font-weight: 700; color: {COLORS['federal_blue']};">PR {pr_value}</span>
                </div>
                <div style="font-size: 0.85rem; color: #475569;"><strong>趨勢：</strong> {trend_icon} | {trend_text}</div>
            </div>
            """, unsafe_allow_html=True)

def main():
    with st.spinner("Loading FRED Data (Loading 10 Years History)..."): 
        df = load_data()
    if df.empty: st.error("無法取得數據。請檢查 FRED API key。"); return

    latest_date = df.index[-1].strftime("%Y-%m-%d")
    market_analysis = analyze_market_dynamics(df)

    st.title("🏦 US Liquidity Holly Dashboard (聯準會流動性荷儷觀測站)")
    st.markdown(f"**Data Source:** FRED | **Latest:** {latest_date} | **Designed for:** Macro Learners")
    st.divider()

    # === 新增：PDF 匯出按鈕 ===
    components.html(
        f"""
        <script>
        function printDashboard() {{
            window.parent.print();
        }}
        </script>
        <div style="text-align: right;">
            <button onclick="printDashboard()" 
                    style="background-color: {COLORS['federal_blue']}; color: white; 
                           border: none; padding: 10px 20px; border-radius: 5px; 
                           cursor: pointer; font-family: sans-serif; font-weight: bold;
                           box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                📄 匯出白皮書報告 (PDF)
            </button>
        </div>
        """,
        height=60
    )
    # =========================

    render_ai_broadcast(df)
    render_health_score(market_analysis)
    render_water_tanks(df.ffill().iloc[-1])
    st.divider()
    render_interest_rates(df)
    st.divider()
    render_market_insights(market_analysis)
    st.divider()
    render_sparklines(df)

if __name__ == "__main__":
    main()