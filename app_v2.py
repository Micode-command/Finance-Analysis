"""
US Liquidity Holly Dashboard - Taiwan Quant Edition (With 10-Year PR Engine UI)
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fed_data_v2 import fetch_fed_data, generate_ai_summary

# === DESIGN SYSTEM ===
COLORS = {"canvas": "#FFFFFF", "ink": "#0F172A", "federal_blue": "#0044CC", "tech_silver": "#E2E8F0", "emerald": "#10B981", "red": "#EF4444", "amber": "#F59E0B"}

st.set_page_config(page_title="財測觀測站", page_icon="🏦", layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""
<style>
    .stApp {{ background-color: {COLORS['canvas']}; }}
    * {{ font-family: 'Inter', sans-serif; color: {COLORS['ink']}; }}
    .metric-card {{ background-color: #F8FAFC; border: 1px solid {COLORS['tech_silver']}; padding: 15px; border-radius: 8px; height: 100%; display: flex; flex-direction: column; justify-content: space-between; position: relative; }}
    .metric-title {{ font-size: 1.1rem; font-weight: 800; color: {COLORS['federal_blue']}; margin-bottom: 8px; padding-right: 60px; }}
    .metric-desc {{ font-size: 0.85rem; color: #475569; margin-bottom: 12px; line-height: 1.5; flex-grow: 1; }}
    .metric-value {{ font-size: 1.6rem; font-weight: 800; }}
    .metric-date {{ font-size: 0.75rem; color: #94A3B8; margin-bottom: 5px; }}
    .deviation-positive {{ color: {COLORS['emerald']}; font-weight: 700; font-size: 0.9rem; }}
    .deviation-negative {{ color: {COLORS['red']}; font-weight: 700; font-size: 0.9rem; }}
    .highlight-pill {{ background-color: #E2E8F0; padding: 2px 6px; border-radius: 4px; font-weight: 600; color: #0F172A; }}
    .pr-badge {{ position: absolute; top: 15px; right: 15px; padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def load_data(): 
    return fetch_fed_data()

# ==========================================
# 核心視覺化函數 (掛載 10 年 PR 值引擎)
# ==========================================
def draw_trend_card(df: pd.DataFrame, column: str, title: str, desc: str, invert_color: bool = False, val_format: str = "{:.2f}", prefix: str = "", suffix: str = "", ma_window: int = 30, absolute_only: bool = False):
    if column not in df.columns:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-desc'>{desc}</div><div>無數據</div></div>", unsafe_allow_html=True)
        return

    valid_data = df[column].dropna()
    if valid_data.empty or len(valid_data) < ma_window:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-desc'>{desc}</div><div>數據不足</div></div>", unsafe_allow_html=True)
        return

    # 1. 計算短線趨勢與乖離率
    s_period = valid_data.tail(ma_window)
    current_val = s_period.iloc[-1]
    last_date = s_period.index[-1].strftime("%Y-%m-%d")
    avg_val = s_period.mean()
    
    deviation = current_val - avg_val
    deviation_pct = (deviation / abs(avg_val)) * 100 if avg_val != 0 else 0

    # 2. 動態計算歷史 10 年 PR 值
    pr_val = None
    pr_html = ""
    if len(valid_data) >= 252: # 至少有 1 年以上的數據才算 PR
        if absolute_only or column in ['VIX', 'High_Yield_Spread', 'DXY', 'USDTWD']:
            # 循環震盪型/結構型：看絕對數值 PR
            pr_val = valid_data.rank(pct=True).iloc[-1] * 100
            # 倒掛利差特殊處理：越小越危險，所以反轉 PR
            if column == "Yield_Curve": pr_val = (1.0 - valid_data.rank(pct=True).iloc[-1]) * 100
        else:
            # 長期成長型：看 120 天均線乖離率的 PR
            ma120 = valid_data.rolling(window=120).mean()
            dev_history = ((valid_data - ma120) / ma120).dropna()
            if not dev_history.empty:
                pr_val = dev_history.rank(pct=True).iloc[-1] * 100

    # 生成 PR 值 UI 標籤
    if pr_val is not None:
        if pr_val >= 80:
            pr_style = "background-color: #FEE2E2; color: #DC2626; border: 1px solid #F87171;"
            pr_text = f"🔥 PR {pr_val:.0f} (過熱/危險)"
        elif pr_val <= 20:
            pr_style = "background-color: #D1FAE5; color: #059669; border: 1px solid #34D399;"
            pr_text = f"🧊 PR {pr_val:.0f} (超跌/低檔)"
        else:
            pr_style = "background-color: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1;"
            pr_text = f"📊 PR {pr_val:.0f}"
        pr_html = f"<div class='pr-badge' style='{pr_style}'>{pr_text}</div>"

    # 3. 決定走勢顏色
    is_up = deviation >= 0
    if invert_color:
        line_color = COLORS['red'] if is_up else COLORS['emerald']
        dev_class = "deviation-negative" if is_up else "deviation-positive"
    else:
        line_color = COLORS['emerald'] if is_up else COLORS['red']
        dev_class = "deviation-positive" if is_up else "deviation-negative"
        
    dev_sign = "+" if is_up else ""
    val_str = f"{prefix}{val_format.format(current_val)}{suffix}"

    # 4. 畫圖
    fig = go.Figure()
    if not absolute_only:
        fig.add_trace(go.Scatter(x=[s_period.index[0], s_period.index[-1]], y=[avg_val, avg_val], mode='lines', line=dict(color=COLORS['tech_silver'], width=2, dash='dash'), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=s_period.index, y=s_period.values, mode='lines', line=dict(color=line_color, width=3), hovertemplate='%{x|%m-%d}: %{y:.2f}<extra></extra>'))
    fig.update_layout(height=70, margin=dict(l=0, r=0, t=5, b=0), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, showgrid=False), yaxis=dict(visible=False, showgrid=False))

    if absolute_only: dev_label = f"<span style='color: {COLORS['ink']}; font-size: 0.85rem; font-weight: 600;'>絕對位階 (看指標說明)</span>"
    else:
        ma_name = "月線" if ma_window <= 30 else "半年線"
        dev_label = f"<span class='{dev_class}'>{dev_sign}{deviation_pct:.1f}% (距{ma_name})</span>"

    st.markdown(f"""
        <div class="metric-card">
            {pr_html}
            <div>
                <div class="metric-title">{title}</div>
                <div class="metric-desc">{desc}</div>
                <div class="metric-date">資料日期: {last_date}</div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 5px;">
                <span class="metric-value">{val_str}</span>
                {dev_label}
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ==========================================
# 台股量化健康分數 (動態連續計分版)
# ==========================================
def render_taiwan_health_score(df: pd.DataFrame, macro_insight: str = ""):
    score = 50
    details = []
    dynamic_desc = []

    def get_dev_pct(col, window=20): # 改用 20MA 月線計算精準乖離
        if col not in df.columns: return 0
        s = df[col].dropna()
        if len(s) < window: return 0
        ma = s.tail(window).mean()
        return ((s.iloc[-1] - ma) / ma) * 100

    # 1. 費城半導體 (權重: +/- 25)
    sox_dev = get_dev_pct('SOX')
    sox_score = max(-25, min(25, sox_dev * 5)) # 乖離越大，加/扣分越多
    score += sox_score
    if sox_dev > 3: dynamic_desc.append("費半強勢撐盤")
    elif sox_dev < -3: dynamic_desc.append("費半弱勢拖累")
    details.append(f"{'🟢' if sox_score>=0 else '🔴'} 費半距月線 {sox_dev:+.1f}% ({sox_score:+.0f}分)")

    # 2. 台幣匯率 (權重: +/- 25，反向指標)
    twd_dev = get_dev_pct('USDTWD')
    twd_score = max(-25, min(25, twd_dev * -20)) # 匯率波動小，乘數放大
    score += twd_score
    if twd_dev > 0.5: dynamic_desc.append("台幣顯著貶值(外資提款壓力)")
    elif twd_dev < -0.5: dynamic_desc.append("台幣強勢升值(熱錢匯入)")
    details.append(f"{'🟢' if twd_score>=0 else '🔴'} 台幣距月線 {twd_dev:+.2f}% ({twd_score:+.0f}分)")

    # 3. 科技股大盤 QQQ (權重: +/- 15)
    qqq_dev = get_dev_pct('QQQ')
    qqq_score = max(-15, min(15, qqq_dev * 4))
    score += qqq_score
    details.append(f"{'🟢' if qqq_score>=0 else '🔴'} 美科技股距月線 {qqq_dev:+.1f}% ({qqq_score:+.0f}分)")

    # 4. 銅博士需求 (權重: +/- 10)
    copper_dev = get_dev_pct('Copper')
    copper_score = max(-10, min(10, copper_dev * 3))
    score += copper_score
    if copper_dev > 3: dynamic_desc.append("實體需求增溫")
    details.append(f"{'🟢' if copper_score>=0 else '🔴'} 銅價距月線 {copper_dev:+.1f}% ({copper_score:+.0f}分)")

    # 5. VIX 恐慌指數 (權重: +10 到 -30)
    if 'VIX' in df.columns:
        vix_val = df['VIX'].dropna().iloc[-1]
        if vix_val < 15:
            vix_score = 10; details.append(f"🟢 VIX 安定 <15 (+10分)")
        elif vix_val > 25:
            vix_score = -25; dynamic_desc.append("華爾街極度恐慌"); details.append(f"🚨 VIX 恐慌 >25 (-25分)")
        elif vix_val > 20:
            vix_score = -10; dynamic_desc.append("避險情緒升溫"); details.append(f"🔴 VIX 警戒 >20 (-10分)")
        else:
            vix_score = 0; details.append(f"⚪ VIX 震盪正常 (0分)")
        score += vix_score

    # ★ 新增：6. 美國淨流動性 4 週動能 (權重: +/- 20)
    if 'Liquidity_ROC_4W' in df.columns:
        liq_roc = df['Liquidity_ROC_4W'].dropna().iloc[-1]
        # 假設流動性每增減 1%，健康度加減 5 分 (可依據實測盤感微調 multiplier)
        liq_score = max(-20, min(20, liq_roc * 5)) 
        score += liq_score
        
        if liq_roc > 2:
            dynamic_desc.append("聯準會資金強烈擴張 🌊")
            details.append(f"🟢 淨資金擴張 {liq_roc:+.2f}% ({liq_score:+.0f}分)")
        elif liq_roc > 0:
            details.append(f"🟢 淨資金溫和注水 {liq_roc:+.2f}% ({liq_score:+.0f}分)")
        elif liq_roc > -2:
            details.append(f"🔴 淨資金溫和收水 {liq_roc:+.2f}% ({liq_score:+.0f}分)")
        else:
            dynamic_desc.append("市場資金急遽抽離 ⚠️")
            details.append(f"🚨 淨資金抽離 {liq_roc:+.2f}% ({liq_score:+.0f}分)")

    # 結算最終分數 (限制在 0-100)
    score = max(0, min(100, score))

    # 動態定調
    if score >= 80: color, status = COLORS['emerald'], "極度狂熱 (積極做多，但需留意乖離過大拉回)"
    elif score >= 60: color, status = COLORS['emerald'], "健康偏多 (沿均線順勢操作，拉回找買點)"
    elif score >= 40: color, status = COLORS['amber'], "震盪整理 (多空交戰，控制資金水位觀望)"
    elif score >= 20: color, status = COLORS['red'], "資金退潮 (跌破均線，提高現金比例防禦)"
    else: color, status = COLORS['red'], "恐慌殺盤 (系統性風險爆發，抱緊現金與避險資產)"

    # 自動組合盤勢特徵診斷
    if dynamic_desc:
        status_subtitle = "💡 當前盤勢特徵：" + "，".join(dynamic_desc) + "。"
    else:
        status_subtitle = "💡 當前盤勢特徵：各項指標於月線附近震盪，多空方向不明確。"

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); border: 2px solid {color}; border-radius: 12px; padding: 25px; margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h2 style="margin: 0; color: {COLORS['ink']}; font-weight: 800;">🇹🇼 台股量化健康度 (Taiwan Market Health)</h2>
                <h4 style="margin: 8px 0 5px 0; color: {color}; font-size: 1.2rem;">{status}</h4>
                <div style="font-size: 0.95rem; font-weight: 700; color: #334155; margin-bottom: 10px; padding: 6px 10px; background-color: #F1F5F9; border-radius: 6px; display: inline-block;">{status_subtitle}</div>
                <div style="font-size: 0.95rem; color: #0F172A; margin-top: 5px; margin-bottom: 10px; padding: 12px; background-color: #EFF6FF; border-left: 4px solid #3B82F6; border-radius: 6px; line-height: 1.6;">
                    {macro_insight}
                </div>
                <div style="font-size: 0.85rem; color: #64748B;">依據各項指標與月線的「實際乖離率」進行連續性動態加減分。</div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 4rem; font-weight: 900; color: {color}; line-height: 1;">{int(score)}</div>
                <div style="font-size: 1rem; color: #64748B; font-weight: bold;">/ 100 分</div>
            </div>
        </div>
        <hr style="border-color: {COLORS['tech_silver']}; margin: 15px 0;">
        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
            {' '.join([f'<span class="highlight-pill" style="border: 1px solid {COLORS["tech_silver"]};">{d}</span>' for d in details])}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 主程式
# ==========================================
def main():
    import os
    st.title("🏦 荷莉總經觀測站 (Holly Dashboard)")
    st.markdown("專為一般人設計的財富自由導航！打破金融黑話，每日花 1 分鐘看懂全球資金流向與系統風險。")
    
    with st.spinner("⏳ 正在從聯準會與華爾街同步最新數據 (計算 10 年 PR 值中)..."): 
        df = load_data()
    
    if df.empty: 
        st.error("無法取得數據。請檢查網路或 API key。")
        return

    # === 資料預處理 === (保留你原本的所有 df 計算邏輯)
    if 'SOFR' in df.columns and 'IORB' in df.columns:
        df['Liquidity_Spread'] = df['SOFR'] - df['IORB']
    if 'DGS10' in df.columns and 'DGS2' in df.columns:
        df['Yield_Curve'] = df['DGS10'] - df['DGS2']
    if 'Reserve_Balances' in df.columns:
        df['Reserves_T'] = df['Reserve_Balances'] / 1e6
    if 'ON_RRP' in df.columns:
        df['RRP_T'] = df['ON_RRP'] / 1e6
        
    if 'Wilshire_5000' in df.columns and 'US_GDP' in df.columns:
        df['US_GDP'] = df['US_GDP'].ffill().bfill()
        df['Wilshire_5000'] = df['Wilshire_5000'].ffill()
        df['Buffett'] = (df['Wilshire_5000'] / df['US_GDP']) * 100
    elif 'SPY' in df.columns:
        df['Buffett'] = (df['SPY'] / df['SPY'].mean()) * 120 

    if 'Buffett' in df.columns:
        df['Buffett_PR'] = df['Buffett'].rank(pct=True) * 100

    if 'Total_Assets' in df.columns and 'TGA_Account' in df.columns and 'ON_RRP' in df.columns:
        df['Net_Liquidity'] = df['Total_Assets'] - df['TGA_Account'] - df['ON_RRP']
        df['Liquidity_ROC_4W'] = df['Net_Liquidity'].pct_change(periods=20) * 100

    if 'Core_PCE' in df.columns:
        df['Core_PCE_YoY'] = df['Core_PCE'].pct_change(periods=252) * 100

    if 'Unemployment_Rate' in df.columns:
        df['U3_MA3'] = df['Unemployment_Rate'].rolling(window=63).mean()
        df['U3_MA3_min12'] = df['U3_MA3'].rolling(window=252).min()
        df['Sahm_Indicator'] = df['U3_MA3'] - df['U3_MA3_min12']

    # ★ 關鍵：在這裡提早呼叫 AI
    api_key = os.environ.get("GEMINI_API_KEY") or (st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None)
    if "ai_data" not in st.session_state and api_key:
        with st.spinner("🤖 正在結合五大防線與最新新聞進行深度解讀..."):
            st.session_state.ai_data = generate_ai_summary(df, api_key)
            
    ai_result = st.session_state.ai_data if "ai_data" in st.session_state else {}
    macro_insight = ai_result.get("macro_phase_insight", "💡 尚未取得 AI 總經觀測，請點擊重新解讀或檢查 API。")

    # 渲染 UI
    render_taiwan_health_score(df, macro_insight) # 把 AI 總評塞進去
    render_ai_broadcast(ai_result) # 直接傳入結果


    # ★ 實體經濟 1：核心 PCE 物價指數年增率 (YoY)
    if 'Core_PCE' in df.columns:
        # 日資料 DataFrame 中，一年約為 252 個交易日
        df['Core_PCE_YoY'] = df['Core_PCE'].pct_change(periods=252) * 100

    # ★ 實體經濟 2：薩姆規則 (Sahm Rule) 衰退指標
    if 'Unemployment_Rate' in df.columns:
        # 3 個月約為 63 個交易日
        df['U3_MA3'] = df['Unemployment_Rate'].rolling(window=63).mean()
        # 尋找過去 12 個月 (252 日) 內的 3 個月均線最低點
        df['U3_MA3_min12'] = df['U3_MA3'].rolling(window=252).min()
        # 薩姆指標：當前 3 個月均線 - 過去 12 個月內的最低 3 個月均線
        df['Sahm_Indicator'] = df['U3_MA3'] - df['U3_MA3_min12']

    st.divider()
    st.subheader("🛡️ 第一道防線：美股大盤與板塊 (反映企業健康度)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "SPY", "標普500 (SPY)", "<b>代表：</b>美國前500大企業 (蘋果、微軟)。<br><b>怎麼看：</b>美國國運基本盤。大盤穩，代表天下太平。", ma_window=30)
    with c2: draw_trend_card(df, "QQQ", "那斯達克100 (QQQ)", "<b>代表：</b>科技巨頭 (輝達、Meta、Google)。<br><b>怎麼看：</b>AI 熱錢火車頭！只要它繼續漲，科技股狂歡就不會停。", ma_window=30)
    with c3: draw_trend_card(df, "IWM", "羅素2000 (IWM)", "<b>代表：</b>2000家美國中小企業。<br><b>怎麼看：</b>若 QQQ 大漲但它大跌，代表大公司正在吸血，中小企業快活不下去了！", ma_window=30)
    with c4: draw_trend_card(df, "XLP", "必需消費板塊 (XLP)", "<b>代表：</b>可口可樂、寶僑、好市多。<br><b>怎麼看：</b>若科技股大跌它卻大漲，代表「聰明錢」提早逃跑，進入防禦避風港。", ma_window=30)

    st.divider()
    st.subheader("🇹🇼 補充防線：台股投資人專屬風向球")
    c1, c2, c3 = st.columns(3)
    with c1: draw_trend_card(df, "SOX", "費城半導體 (SOX)", "<b>代表：</b>全球晶片廠大本營 (台積電ADR、艾司摩爾)。<br><b>怎麼看：</b>台股直接命脈。費半大跌，隔天台股電子股絕對被血洗。", ma_window=30)
    with c2: draw_trend_card(df, "Copper", "銅博士期貨", "<b>代表：</b>製造業的基礎原料。<br><b>怎麼看：</b>價格暴跌代表全世界工廠不敢進貨、實體訂單嚴重萎縮。", prefix="$", ma_window=30)
    with c3: draw_trend_card(df, "USDTWD", "美元兌台幣匯率", "<b>怎麼看：</b>外資的提款機。<span class='highlight-pill'>數字變大(向上)</span> 代表台幣貶值，外資正在瘋狂賣出台股匯出台灣！", invert_color=True, ma_window=30)

    st.divider()
    st.subheader("💣 第二/三道防線：黑天鵝警報與全球匯率戰 (看長期趨勢)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "VIX", "恐慌指數 (VIX)", "<b>怎麼看：</b>華爾街避險情緒。大於20警戒；<span class='highlight-pill'>大於30</span> 代表市場正在發生恐慌性崩盤拋售！", invert_color=True, ma_window=120)
    with c2: draw_trend_card(df, "High_Yield_Spread", "垃圾債利差", "<b>怎麼看：</b>體質差的企業借錢要多付的利息。<span class='highlight-pill'>飆升(向上)</span> 代表銀行「抽銀根」拒絕借錢，企業倒閉潮即將來臨！", invert_color=True, suffix="%", ma_window=120)
    with c3: draw_trend_card(df, "DXY", "美元指數 (DXY)", "<b>怎麼看：</b><span class='highlight-pill'>數字變大(向上)</span> 代表美元太強勢，會把全球(包含台灣)的熱錢全部吸回美國，造成台股大跌。", invert_color=True, ma_window=120)
    with c4: draw_trend_card(df, "USDJPY", "美元兌日圓", "<b>怎麼看：</b><span class='highlight-pill'>數字變小(向下)</span> 代表日圓升值。大戶借便宜日圓炒股的利息暴增，被迫賣美股還錢，引發全球股災。", invert_color=True, ma_window=120)

    st.divider()
    st.subheader("🛢️ 第四道防線：通膨萬惡之源與股市泡沫")
    c1, c2, c3 = st.columns(3)
    with c1: draw_trend_card(df, "WTI", "WTI 西德州原油", "<b>怎麼看：</b>只要油價居高不下，通膨就壓不下來，聯準會就不可能降息救市。", invert_color=True, prefix="$", ma_window=120)
    with c2: draw_trend_card(df, "Gold", "黃金期貨", "<b>怎麼看：</b>當大家怕戰爭、怕通膨、怕鈔票變薄時，就會瘋狂買進黃金保命。", prefix="$", ma_window=120)
    with c3: draw_trend_card(df, "Buffett", "巴菲特指標", "<b>怎麼看：</b>美股總市值 ÷ 美國 GDP。<br><span class='highlight-pill'>大於150%</span> 代表股市處於歷史級嚴重泡沫，股神巴菲特通常會賣股換現金。", invert_color=True, suffix="%", absolute_only=True)

    st.divider()
    st.subheader("🏦 第五道防線：聯準會底層水箱 (水龍頭開關)")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "Reserves_T", "銀行準備金水位", "<b>怎麼看：</b>聯準會供給市場的活水。水位越高，銀行越有底氣借錢給市場去炒股。", suffix=" 兆美元", ma_window=120)
    with c2: draw_trend_card(df, "RRP_T", "ON RRP 備用金", "怎麼看：市場資金的停車場。如果數字快掉到 0，代表用來救火的備用緩衝墊已經乾涸了。", suffix=" 兆美元", absolute_only=True)
    with c3: draw_trend_card(df, "Liquidity_Spread", "短期資金吃緊度", "<b>怎麼看：</b>SOFR與IORB利差。只要變成 <span class='highlight-pill'>大於 0.02%</span>，代表華爾街銀行間周轉困難，大家都在搶現金。", invert_color=True, suffix="%", absolute_only=True)
    with c4: draw_trend_card(df, "Yield_Curve", "長短債利差 (倒掛)", "<b>怎麼看：</b>正常應為正數。若變成 <span class='highlight-pill'>負數(<0，倒掛)</span>，歷史經驗是：倒掛恢復正值的 12~18 個月內會引發經濟大崩盤。", suffix="%", absolute_only=True)

    st.divider()
    st.subheader("🏭 終極防線：實體經濟與通膨 (薩姆衰退雷達)")
    c1, c2, c3 = st.columns(3)
    
    with c1: 
        draw_trend_card(df, "Unemployment_Rate", "美國失業率", 
                        "<b>基準線：</b>4.0% 左右為充分就業。<br>"
                        "<b>怎麼看：</b>絕對數字不重要，關鍵看「趨勢」。若從低點連續幾個月往上跳升，代表企業正在大規模裁員，消費動能即將崩盤。", 
                        invert_color=True, suffix="%", absolute_only=True)
    with c2: 
        draw_trend_card(df, "Sahm_Indicator", "薩姆規則衰退指標", 
                        "<b>公式：</b>目前的失業率平均 減去 過去一年的最低點。<br>"
                        "<b>怎麼看：</b>若顯示為 0.00%，代表目前就在歷史低點，完全沒惡化。一旦突破 <span class='highlight-pill'>0.5%</span>，代表經濟衰退已實質發生，股市將迎來主跌段！", 
                        invert_color=True, suffix="%", absolute_only=True)
    with c3: 
        draw_trend_card(df, "Core_PCE_YoY", "核心 PCE 年增率 (個人消費支出)", 
                        "<b>全名：</b>核心個人消費支出物價指數 (已剔除波動大的食品與能源)。<br>"
                        "<b>怎麼算：</b>追蹤民眾「實際花錢買了什麼」。它比 CPI 更精準，因為會考量「替代效應」(如牛肉變貴，民眾改吃豬肉的行為)。<br>"
                        "<b>基準線：</b>聯準會的終極目標為 <span class='highlight-pill'>2.0%</span>。<br>"
                        "<b>怎麼看：</b>聯準會決定「降息與否」的唯一通膨指標。若低於 2%，代表通膨已死，FED 隨時有底氣降息救市；若持續反彈，則降息無望。", 
                        invert_color=True, suffix="%", absolute_only=True)
def render_ai_broadcast(ai_result):
    import plotly.graph_objects as go
    import streamlit as st
    
    broadcast_text = ai_result.get("broadcast", ai_result.get("error", "解盤失敗。"))
    allocation = ai_result.get("allocation_recommendation", {})
    reasons = ai_result.get("allocation_reasons", {})
    market_insights = ai_result.get("market_insights_html", "")

    with st.expander("🎙️ 展開今日荷莉大師級 AI 總經解析", expanded=True):
        st.markdown(broadcast_text, unsafe_allow_html=True)
        if st.button("🔄 重新解讀"):
            del st.session_state.ai_data
            st.rerun()

    if market_insights:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🛡️ 財富穩健自由專屬：今日目標資金配置與實戰劇本")
        
        c1, c2 = st.columns([1, 1.8])
        
        with c1:
            if allocation:
                labels = ['台幣存款', '外幣與公司債', '月配息現金流', '核心股票', '黃金與戰術']
                vals = [
                    allocation.get("twd_cash", 20),
                    allocation.get("usd_assets", 20),
                    allocation.get("cashflow", 20),
                    allocation.get("core_growth", 20),
                    allocation.get("tactical_hedge", 20)
                ]
                colors = ['#94A3B8', '#0284C7', '#10B981', '#F59E0B', '#EF4444']
                
                # 圓餅圖：取消外部圖例，只在內部顯示純百分比
                fig_pie = go.Figure(data=[go.Pie(
                    labels=labels, 
                    values=vals, 
                    hole=.45, 
                    marker=dict(colors=colors, line=dict(color='#FFFFFF', width=2)),
                    textinfo='percent', 
                    textfont=dict(size=16, color='#FFFFFF'),
                    hoverinfo='label+percent'
                )])
                
                fig_pie.update_layout(
                    margin=dict(t=0, b=15, l=0, r=0), 
                    showlegend=False,  # 👈 解決白色幽靈圖例的關鍵：直接關掉！
                    height=280, 
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False})
                
                # 在圓餅圖下方，自製「專屬用途小區塊」
                st.markdown(f"""
                <div style="font-size: 0.95rem; line-height: 1.5;">
                    <div style="border-left: 4px solid #94A3B8; padding-left: 8px; margin-bottom: 12px;">
                        <b>台幣存款 ({vals[0]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("twd_cash", "防禦保命底層")}</span>
                    </div>
                    <div style="border-left: 4px solid #0284C7; padding-left: 8px; margin-bottom: 12px;">
                        <b>外幣與公司債 ({vals[1]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("usd_assets", "對抗匯率與鎖利")}</span>
                    </div>
                    <div style="border-left: 4px solid #10B981; padding-left: 8px; margin-bottom: 12px;">
                        <b>月配息現金流 ({vals[2]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("cashflow", "股市震盪護城河")}</span>
                    </div>
                    <div style="border-left: 4px solid #F59E0B; padding-left: 8px; margin-bottom: 12px;">
                        <b>核心股票 ({vals[3]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("core_growth", "增值攻擊主軸")}</span>
                    </div>
                    <div style="border-left: 4px solid #EF4444; padding-left: 8px; margin-bottom: 12px;">
                        <b>黃金與戰術 ({vals[4]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("tactical_hedge", "黑天鵝防禦與短打")}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with c2:
            # 渲染右側最新的「大局觀與實戰劇本」
            st.markdown(market_insights, unsafe_allow_html=True)

if __name__ == "__main__":
    main()       