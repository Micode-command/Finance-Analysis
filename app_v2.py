"""
US Liquidity Holly Dashboard - Taiwan Quant Edition
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fed_data_v2 import fetch_fed_data, generate_ai_summary

COLORS = {
    "canvas": "#FFFFFF", "ink": "#0F172A", "federal_blue": "#0044CC", 
    "tech_silver": "#E2E8F0", "emerald": "#10B981", "red": "#EF4444", "amber": "#F59E0B"
}

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
    .prob-box {{ padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #E2E8F0; }}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def load_data(): 
    return fetch_fed_data()

def draw_trend_card(df: pd.DataFrame, column: str, title: str, desc: str, invert_color: bool = False, val_format: str = "{:.2f}", prefix: str = "", suffix: str = "", ma_window: int = 30, absolute_only: bool = False):
    if column not in df.columns:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-desc'>{desc}</div><div style='font-weight:bold; color:#EF4444;'>無數據</div></div>", unsafe_allow_html=True)
        return

    valid_data = df[column].dropna()
    if valid_data.empty or len(valid_data) < ma_window:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-desc'>{desc}</div><div style='font-weight:bold; color:#F59E0B;'>數據不足</div></div>", unsafe_allow_html=True)
        return

    s_period = valid_data.tail(ma_window)
    current_val = s_period.iloc[-1]
    last_date = s_period.index[-1].strftime("%Y-%m-%d")
    avg_val = s_period.mean()
    
    deviation = current_val - avg_val
    deviation_pct = (deviation / abs(avg_val)) * 100 if avg_val != 0 else 0

    pr_val = None
    pr_html = ""
    if len(valid_data) >= 252:
        if absolute_only or column in ['VIX', 'High_Yield_Spread', 'DXY', 'USDTWD']:
            pr_val = valid_data.rank(pct=True).iloc[-1] * 100
            if column == "Yield_Curve": pr_val = (1.0 - valid_data.rank(pct=True).iloc[-1]) * 100
        else:
            ma120 = valid_data.rolling(window=120).mean()
            dev_history = ((valid_data - ma120) / ma120).dropna()
            if not dev_history.empty:
                pr_val = dev_history.rank(pct=True).iloc[-1] * 100

    if pr_val is not None:
        if pr_val >= 80:
            pr_style = "background-color: #FEE2E2; color: #DC2626; border: 1px solid #F87171;"
            pr_text = f"🔥 PR {pr_val:.0f} (過熱)"
        elif pr_val <= 20:
            pr_style = "background-color: #D1FAE5; color: #059669; border: 1px solid #34D399;"
            pr_text = f"🧊 PR {pr_val:.0f} (超跌)"
        else:
            pr_style = "background-color: #F1F5F9; color: #64748B; border: 1px solid #CBD5E1;"
            pr_text = f"📊 PR {pr_val:.0f}"
        pr_html = f"<div class='pr-badge' style='{pr_style}'>{pr_text}</div>"

    is_up = deviation >= 0
    if invert_color:
        line_color = COLORS['red'] if is_up else COLORS['emerald']
        dev_class = "deviation-negative" if is_up else "deviation-positive"
    else:
        line_color = COLORS['emerald'] if is_up else COLORS['red']
        dev_class = "deviation-positive" if is_up else "deviation-negative"
        
    dev_sign = "+" if is_up else ""
    val_str = f"{prefix}{val_format.format(current_val)}{suffix}"

    fig = go.Figure()
    if not absolute_only:
        fig.add_trace(go.Scatter(x=[s_period.index[0], s_period.index[-1]], y=[avg_val, avg_val], mode='lines', line=dict(color=COLORS['tech_silver'], width=2, dash='dash'), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=s_period.index, y=s_period.values, mode='lines', line=dict(color=line_color, width=3), hovertemplate='%{x|%m-%d}: %{y:.2f}<extra></extra>'))
    fig.update_layout(height=70, margin=dict(l=0, r=0, t=5, b=0), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, showgrid=False), yaxis=dict(visible=False, showgrid=False))

    if absolute_only: dev_label = f"<span style='color: {COLORS['ink']}; font-size: 0.85rem; font-weight: 600;'>近期絕對趨勢</span>"
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
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=f"chart_{column}")

def render_taiwan_health_score(df: pd.DataFrame, macro_insight: str = ""):
    score = 50
    details = []
    dynamic_desc = []

    def get_dev_pct(col, window=20): 
        if col not in df.columns: return 0
        s = df[col].dropna()
        if len(s) < window: return 0
        ma = s.tail(window).mean()
        return ((s.iloc[-1] - ma) / ma) * 100

    sox_dev = get_dev_pct('SOX')
    sox_score = max(-25, min(25, sox_dev * 5)) 
    score += sox_score
    if sox_dev > 3: dynamic_desc.append("費半強勢撐盤")
    elif sox_dev < -3: dynamic_desc.append("費半弱勢拖累")
    details.append(f"{'🟢' if sox_score>=0 else '🔴'} 費半距月線 {sox_dev:+.1f}% ({sox_score:+.0f}分)")

    twd_dev = get_dev_pct('USDTWD')
    twd_score = max(-25, min(25, twd_dev * -20)) 
    score += twd_score
    if twd_dev > 0.5: dynamic_desc.append("台幣貶值壓力")
    elif twd_dev < -0.5: dynamic_desc.append("台幣升值熱錢")
    details.append(f"{'🟢' if twd_score>=0 else '🔴'} 台幣距月線 {twd_dev:+.2f}% ({twd_score:+.0f}分)")

    qqq_dev = get_dev_pct('QQQ')
    qqq_score = max(-15, min(15, qqq_dev * 4))
    score += qqq_score
    details.append(f"{'🟢' if qqq_score>=0 else '🔴'} 美科技股距月線 {qqq_dev:+.1f}% ({qqq_score:+.0f}分)")

    copper_dev = get_dev_pct('Copper')
    copper_score = max(-10, min(10, copper_dev * 3))
    score += copper_score
    if copper_dev > 3: dynamic_desc.append("實體需求增溫")
    details.append(f"{'🟢' if copper_score>=0 else '🔴'} 銅價距月線 {copper_dev:+.1f}% ({copper_score:+.0f}分)")

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

    if 'Liquidity_ROC_4W' in df.columns:
        liq_roc = df['Liquidity_ROC_4W'].dropna().iloc[-1]
        liq_score = max(-20, min(20, liq_roc * 5)) 
        score += liq_score
        
        if liq_roc > 2:
            dynamic_desc.append("聯準會資金強烈擴張")
            details.append(f"🟢 淨資金擴張 {liq_roc:+.2f}% ({liq_score:+.0f}分)")
        elif liq_roc > 0:
            details.append(f"🟢 淨資金注水 {liq_roc:+.2f}% ({liq_score:+.0f}分)")
        elif liq_roc > -2:
            details.append(f"🔴 淨資金收水 {liq_roc:+.2f}% ({liq_score:+.0f}分)")
        else:
            dynamic_desc.append("市場資金抽離")
            details.append(f"🚨 淨資金抽離 {liq_roc:+.2f}% ({liq_score:+.0f}分)")

    score = max(0, min(100, score))

    if score >= 80: color, status = COLORS['emerald'], "極度狂熱 (留意拉回)"
    elif score >= 60: color, status = COLORS['emerald'], "健康偏多 (順勢操作)"
    elif score >= 40: color, status = COLORS['amber'], "震盪整理 (控制資金)"
    elif score >= 20: color, status = COLORS['red'], "資金退潮 (提高現金防禦)"
    else: color, status = COLORS['red'], "恐慌殺盤 (抱緊避險資產)"

    status_subtitle = ("💡 盤勢特徵：" + "，".join(dynamic_desc) + "。") if dynamic_desc else "💡 盤勢特徵：多空不明。"

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #F8FAFC 0%, #FFFFFF 100%); border: 2px solid {color}; border-radius: 12px; padding: 25px; margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h2 style="margin: 0; color: {COLORS['ink']}; font-weight: 800;">🇹🇼 台股量化健康度</h2>
                <h4 style="margin: 8px 0 5px 0; color: {color}; font-size: 1.2rem;">{status}</h4>
                <div style="font-size: 0.95rem; font-weight: 700; color: #334155; margin-bottom: 10px; padding: 6px 10px; background-color: #F1F5F9; border-radius: 6px; display: inline-block;">{status_subtitle}</div>
                <div style="font-size: 0.95rem; color: #0F172A; margin-top: 5px; margin-bottom: 10px; padding: 12px; background-color: #EFF6FF; border-left: 4px solid #3B82F6; border-radius: 6px; line-height: 1.6;">
                    {macro_insight}
                </div>
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

def render_ai_broadcast(ai_result):
    broadcast_text = ai_result.get("broadcast", ai_result.get("error", "解盤失敗。"))
    allocation = ai_result.get("allocation_recommendation", {})
    reasons = ai_result.get("allocation_reasons", {})
    market_insights = ai_result.get("market_insights_html", "")

    with st.expander("🎙️ 展開今日荷莉大師級 AI 總經解析", expanded=True):
        st.markdown(broadcast_text, unsafe_allow_html=True)
        if st.button("🔄 重新解讀", key="btn_rerun"):
            if "ai_data" in st.session_state: del st.session_state.ai_data
            st.rerun()

    if market_insights:
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🛡️ 今日目標資金配置與實戰劇本")
        c1, c2 = st.columns([1, 1.8])
        with c1:
            if allocation:
                labels = ['台幣存款', '外幣與公司債', '月配息現金流', '核心股票', '黃金與戰術']
                vals = [allocation.get("twd_cash", 20), allocation.get("usd_assets", 20), allocation.get("cashflow", 20), allocation.get("core_growth", 20), allocation.get("tactical_hedge", 20)]
                colors = ['#94A3B8', '#0284C7', '#10B981', '#F59E0B', '#EF4444']
                fig_pie = go.Figure(data=[go.Pie(labels=labels, values=vals, hole=.45, marker=dict(colors=colors, line=dict(color='#FFFFFF', width=2)), textinfo='percent', textfont=dict(size=16, color='#FFFFFF'))])
                fig_pie.update_layout(margin=dict(t=0, b=15, l=0, r=0), showlegend=False, height=280, paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True, config={'displayModeBar': False}, key="pie_chart")
                
                st.markdown(f"""
                <div style="font-size: 0.95rem; line-height: 1.5;">
                    <div style="border-left: 4px solid #94A3B8; padding-left: 8px; margin-bottom: 12px;"><b>台幣存款 ({vals[0]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("twd_cash", "防禦保命")}</span></div>
                    <div style="border-left: 4px solid #0284C7; padding-left: 8px; margin-bottom: 12px;"><b>外幣與公司債 ({vals[1]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("usd_assets", "鎖利防禦")}</span></div>
                    <div style="border-left: 4px solid #10B981; padding-left: 8px; margin-bottom: 12px;"><b>月配息現金流 ({vals[2]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("cashflow", "震盪護城河")}</span></div>
                    <div style="border-left: 4px solid #F59E0B; padding-left: 8px; margin-bottom: 12px;"><b>核心股票 ({vals[3]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("core_growth", "資本攻擊")}</span></div>
                    <div style="border-left: 4px solid #EF4444; padding-left: 8px; margin-bottom: 12px;"><b>黃金與戰術 ({vals[4]}%)</b><br><span style="color:#475569; font-size: 0.85rem;">{reasons.get("tactical_hedge", "黑天鵝防禦")}</span></div>
                </div>
                """, unsafe_allow_html=True)
        with c2:
            st.markdown(market_insights, unsafe_allow_html=True)

def render_bottom_fishing_signals(df):
    st.divider()
    st.subheader("🚦 機構級抄底/逃頂：四大長線買入確認信號")
    st.markdown("當以下 **4 個條件滿足 3 個以上**時，代表系統性風險解除，是重新大舉買入長期風險資產的歷史級時刻。")
    
    brent_val = df['Brent'].dropna().iloc[-1] if 'Brent' in df.columns else 100.0
    cpi_yoy = df['CPI_YoY'].dropna().iloc[-1] if 'CPI_YoY' in df.columns else 5.0
    dgs10_val = df['DGS10'].dropna().iloc[-1] if 'DGS10' in df.columns else 5.0
    
    dgs2_val = df['DGS2'].dropna().iloc[-1] if 'DGS2' in df.columns else 5.0
    iorb_val = df['IORB'].dropna().iloc[-1] if 'IORB' in df.columns else 5.0
    rate_cut_priced_in = dgs2_val < (iorb_val - 0.25)
    
    cond_1 = brent_val < 90.0
    cond_2 = cpi_yoy < 2.5
    cond_3 = dgs10_val < 4.3
    cond_4 = rate_cut_priced_in
    
    signals_met = sum([cond_1, cond_2, cond_3, cond_4])
    
    def get_card_html(title, current_val, target, is_met, unit="", reverse=False):
        bg_color = "#ECFDF5" if is_met else "#F8FAFC"
        border_color = "#10B981" if is_met else "#CBD5E1"
        icon = "✅" if is_met else "⏳"
        status_color = "#059669" if is_met else "#64748B"
        return f"""
        <div style="background-color: {bg_color}; border: 2px solid {border_color}; border-radius: 8px; padding: 15px; text-align: center; height: 100%;">
            <div style="font-size: 1.5rem; margin-bottom: 5px;">{icon}</div>
            <div style="font-weight: 800; color: #0F172A; font-size: 1.05rem;">{title}</div>
            <div style="margin-top: 8px; font-size: 0.9rem; color: #475569;">目標: <span style="font-weight:bold;">{target}</span></div>
            <div style="margin-top: 5px; font-size: 1.2rem; font-weight: 900; color: {status_color};">當前: {current_val:.2f}{unit}</div>
        </div>
        """

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(get_card_html("1. 原油解除通膨警報", brent_val, "< $90", cond_1, "$"), unsafe_allow_html=True)
    with c2: st.markdown(get_card_html("2. 廣義 CPI 實質降溫", cpi_yoy, "< 2.5%", cond_2, "%"), unsafe_allow_html=True)
    with c3: st.markdown(get_card_html("3. 10年期美債殖利率回落", dgs10_val, "< 4.3%", cond_3, "%"), unsafe_allow_html=True)
    with c4: 
        status_text = "已定價降息" if cond_4 else "緊縮/高位震盪"
        bg_color = "#ECFDF5" if cond_4 else "#F8FAFC"
        border_color = "#10B981" if cond_4 else "#CBD5E1"
        st.markdown(f"""
        <div style="background-color: {bg_color}; border: 2px solid {border_color}; border-radius: 8px; padding: 15px; text-align: center; height: 100%;">
            <div style="font-size: 1.5rem; margin-bottom: 5px;">{'✅' if cond_4 else '⏳'}</div>
            <div style="font-weight: 800; color: #0F172A; font-size: 1.05rem;">4. 聯準會降息信號發出</div>
            <div style="margin-top: 8px; font-size: 0.9rem; color: #475569;">量化標準: <span style="font-weight:bold;">2年債 < 基準利率1碼</span></div>
            <div style="margin-top: 5px; font-size: 1.1rem; font-weight: 900; color: {'#059669' if cond_4 else '#64748B'};">{status_text}</div>
        </div>
        """, unsafe_allow_html=True)
        
    if signals_met >= 3:
        st.success(f"🔥 歷史級長線買點浮現！目前已滿足 {signals_met}/4 項機構抄底條件，可開始將資金大舉轉向風險資產 (股票/長債)。")
    else:
        st.warning(f"⚠️ 目前僅滿足 {signals_met}/4 項條件。資金應保持防禦姿態 (現金/短債/月配息)，等待流動性拐點。")

def main():
    st.title("🏦 荷莉總經觀測站 (Holly Dashboard)")
    st.markdown("專為一般人設計的財富自由導航！打破金融黑話，每日花 1 分鐘看懂全球資金流向與系統風險。")
    
    with st.spinner("⏳ 正在從聯準會與華爾街同步最新數據..."): 
        df_raw = load_data()
    
    if df_raw.empty: 
        st.error("無法取得數據。請檢查網路或 API key。")
        return

    df = df_raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if col[0] else col[1] for col in df.columns]
    df.columns = [str(c).strip() for c in df.columns]

    df = df.ffill().bfill()

    # === ⚡ 植入高頻戰術變數 ===
    if 'USDTWD' in df.columns:
        df['USDTWD_ROC_5D'] = df['USDTWD'].pct_change(periods=5) * 100
    if 'High_Yield_Spread' in df.columns:
        df['HY_Spread_Chg_5D'] = df['High_Yield_Spread'].diff(periods=5)
    if 'VIX' in df.columns:
        df['VIX_MA20'] = df['VIX'].rolling(window=20).mean()
        df['VIX_Dev_20D'] = ((df['VIX'] - df['VIX_MA20']) / df['VIX_MA20']) * 100
    
    # === 原有資料預處理 ===
    if 'CPI' in df.columns: 
        df['CPI_YoY'] = df['CPI'].pct_change(periods=252) * 100
    if 'Core_PCE' in df.columns: df['Core_PCE_YoY'] = df['Core_PCE'].pct_change(periods=252) * 100
    if 'SOFR' in df.columns and 'IORB' in df.columns: df['Liquidity_Spread'] = df['SOFR'] - df['IORB']
    if 'DGS10' in df.columns and 'DGS2' in df.columns: df['Yield_Curve'] = df['DGS10'] - df['DGS2']
    if 'Reserve_Balances' in df.columns: df['Reserves_T'] = df['Reserve_Balances'] / 1e6
    if 'ON_RRP' in df.columns: df['RRP_T'] = df['ON_RRP'] / 1e6
        
    if 'Wilshire_5000' in df.columns and 'US_GDP' in df.columns:
        df['Buffett'] = (df['Wilshire_5000'] / df['US_GDP']) * 100
    elif 'SPY' in df.columns:
        df['Buffett'] = (df['SPY'] / df['SPY'].mean()) * 120 

    if 'Buffett' in df.columns: df['Buffett_PR'] = df['Buffett'].rank(pct=True) * 100

    if 'Total_Assets' in df.columns and 'TGA_Account' in df.columns and 'ON_RRP' in df.columns:
        df['Net_Liquidity'] = df['Total_Assets'] - df['TGA_Account'] - df['ON_RRP']
        df['Liquidity_ROC_4W'] = df['Net_Liquidity'].pct_change(periods=20) * 100

    if 'Core_PCE' in df.columns: df['Core_PCE_YoY'] = df['Core_PCE'].pct_change(periods=252) * 100
    if 'Unemployment_Rate' in df.columns:
        df['U3_MA3'] = df['Unemployment_Rate'].rolling(window=63).mean()
        df['U3_MA3_min12'] = df['U3_MA3'].rolling(window=252).min()
        df['Sahm_Indicator'] = df['U3_MA3'] - df['U3_MA3_min12']

    df = df.ffill().bfill()

    import os
    api_key = os.environ.get("GEMINI_API_KEY") or (st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None)
    if "ai_data" not in st.session_state and api_key:
        with st.spinner("🤖 正在結合五大防線與最新新聞進行深度解讀..."):
            st.session_state.ai_data = generate_ai_summary(df, api_key)
            
    ai_result = st.session_state.ai_data if "ai_data" in st.session_state else {}
    macro_insight = ai_result.get("macro_phase_insight", "💡 尚未取得 AI 總經觀測，請點擊重新解讀。")

    # 🛑 修正點：原本這裡重複貼上呼叫了兩次，現已修正為一次！
    render_taiwan_health_score(df, macro_insight) 
    render_ai_broadcast(ai_result) 
    render_bottom_fishing_signals(df)  

    st.divider()
    st.subheader("⚡ 戰術雷達：高頻微觀與籌碼動能 (一週變盤雷達)")
    t1, t2, t3 = st.columns(3)
    with t1: draw_trend_card(df, "USDTWD_ROC_5D", "台幣 5 日動能 (外資生死線)", "<b>怎麼看：</b>大於 +0.5% (急貶) 代表外資急撤；小於 -0.5% 代表熱錢湧入。", invert_color=True, suffix="%", ma_window=20, absolute_only=True)
    with t2: draw_trend_card(df, "HY_Spread_Chg_5D", "垃圾債利差 5 日變化", "<b>怎麼看：</b>大於 0 (正數) 代表華爾街正在抽銀根，信用風險飆升。", invert_color=True, suffix="%", ma_window=20, absolute_only=True)
    with t3: draw_trend_card(df, "VIX_Dev_20D", "VIX 距月線乖離 (情緒偏斜)", "<b>怎麼看：</b>大於 +15% 代表市場極度恐慌；小於 -15% 代表過度貪婪。", invert_color=True, suffix="%", ma_window=20, absolute_only=True)

    st.divider()
    st.subheader("🛡️ 第一道防線：美股大盤與板塊")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "SPY", "標普500 (SPY)", "美國國運基本盤", ma_window=30)
    with c2: draw_trend_card(df, "QQQ", "那斯達克100 (QQQ)", "AI 熱錢火車頭", ma_window=30)
    with c3: draw_trend_card(df, "IWM", "羅素2000 (IWM)", "美國中小企業", ma_window=30)
    with c4: draw_trend_card(df, "XLP", "必需消費板塊 (XLP)", "防禦避風港", ma_window=30)

    st.divider()
    st.subheader("🇹🇼 補充防線：台股風向球")
    c1, c2, c3 = st.columns(3)
    with c1: draw_trend_card(df, "SOX", "費城半導體 (SOX)", "台股直接命脈", ma_window=30)
    with c2: draw_trend_card(df, "Copper", "銅博士期貨", "實體訂單指標", prefix="$", ma_window=30)
    with c3: draw_trend_card(df, "USDTWD", "美元兌台幣", "外資提款機", invert_color=True, ma_window=30)

    st.divider()
    st.subheader("💣 第二/三道防線：黑天鵝與匯率戰")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "VIX", "恐慌指數 (VIX)", "華爾街避險情緒", invert_color=True, ma_window=120)
    with c2: draw_trend_card(df, "High_Yield_Spread", "垃圾債利差", "企業倒閉雷達", invert_color=True, suffix="%", ma_window=120)
    with c3: draw_trend_card(df, "DXY", "美元指數 (DXY)", "全球熱錢吸塵器", invert_color=True, ma_window=120)
    with c4: draw_trend_card(df, "DGS30", "30年期美債殖利率", "長線資金定價之錨", invert_color=True, suffix="%", absolute_only=True)

    st.divider()
    st.subheader("🛢️ 第四道防線：通膨與泡沫")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "Brent", "布倫特原油", "通膨之源", invert_color=True, prefix="$", ma_window=120) 
    with c2: draw_trend_card(df, "Gold", "黃金期貨", "戰爭通膨避險", prefix="$", ma_window=120)
    with c3: draw_trend_card(df, "CPI_YoY", "廣義 CPI 年增率", "通膨絕對指標", invert_color=True, suffix="%", absolute_only=True) 
    with c4: draw_trend_card(df, "Buffett", "巴菲特指標", "歷史級泡沫", invert_color=True, suffix="%", absolute_only=True)

    st.divider()
    st.subheader("🏦 第五道防線：聯準會底層水箱")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "Reserves_T", "銀行準備金", "聯準會活水", suffix=" 兆", ma_window=120)
    with c2: draw_trend_card(df, "RRP_T", "ON RRP 備用金", "救火緩衝墊", suffix=" 兆", absolute_only=True)
    with c3: draw_trend_card(df, "Liquidity_Spread", "短期吃緊度", "華爾街現金荒", invert_color=True, suffix="%", absolute_only=True)
    with c4: draw_trend_card(df, "Yield_Curve", "長短債利差", "衰退領先指標", suffix="%", absolute_only=True)

    st.divider()
    st.subheader("🏭 終極防線：實體經濟衰退雷達")
    c1, c2, c3 = st.columns(3)
    with c1: draw_trend_card(df, "Unemployment_Rate", "美國失業率", "消費動能崩盤前兆", invert_color=True, suffix="%", absolute_only=True)
    with c2: draw_trend_card(df, "Sahm_Indicator", "薩姆衰退指標", "實質衰退觸發器", invert_color=True, suffix="%", absolute_only=True)
    with c3: draw_trend_card(df, "Core_PCE_YoY", "核心 PCE 年增率", "降息唯一指標", invert_color=True, suffix="%", absolute_only=True)

if __name__ == "__main__":
    main()