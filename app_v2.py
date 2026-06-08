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



# 🟢 新增：量化 PR 說明書
st.markdown("""
<div style="background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 12px 16px; border-radius: 4px; margin-bottom: 20px;">
    <div style="font-weight: 800; color: #0F172A; margin-bottom: 6px;">ℹ️ 關於本站的 PR 值 (Percentile Rank) 演算法與顏色指南</div>
    <div style="font-size: 0.85rem; color: #334155; line-height: 1.6;">
        <b>C-PR (Cycle) 週期型：</b>適用於 VIX、利差、美債殖利率等「具備天花板與地板」的指標。PR 99 代表「現在的絕對數值，比過去 10 年裡 99% 的日子還要高」。<br>
        <b>G-120PR (Growth) 中期成長乖離：</b>適用於標普、費半等「長期永遠向上」的股市資產。計算目前股價距離 <b>120 日均線(半年線)</b> 有多遠，再與過去 10 年對比。PR 99 代表中期過熱。<br>
        <b>G-200PR (Growth) 長期成長乖離：</b>同上，但基準為 <b>200 日均線(年線)</b>。PR 99 代表「目前的泡沫/溢價程度，比過去 10 年裡 99% 的日子還要誇張」，為歷史級警報。<br>
        <span style="display:inline-block; margin-top: 6px;"><b>🎨 熱力圖燈號：</b> 
        <span style="background:#991B1B; color:white; padding:2px 6px; border-radius:4px;">深紅 PR 90-100 (極端危險)</span> 
        <span style="background:#EA580C; color:white; padding:2px 6px; border-radius:4px;">橘紅 PR 80-89 (警戒)</span> 
        <span style="background:#F1F5F9; color:#475569; padding:2px 6px; border-radius:4px;">灰白 PR 20-79 (常態)</span> 
        <span style="background:#D1FAE5; color:#065F46; padding:2px 6px; border-radius:4px;">淺綠 PR 10-19 (超跌)</span> 
        <span style="background:#064E3B; color:white; padding:2px 6px; border-radius:4px;">深綠 PR 0-9 (黃金坑)</span>
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# 增加一個側邊欄按鈕來手動清除快取
with st.sidebar:
    st.markdown("### 🛠️ 系統維護")
    if st.button("🧹 清除數據快取 (強制重新抓取)"):
        st.cache_data.clear()
        st.success("快取已清除！請重整網頁。")

@st.cache_data(ttl=3600)
def load_data(): 
    return fetch_fed_data()

def draw_trend_card(df: pd.DataFrame, column: str, title: str, desc: str, invert_color: bool = False, val_format: str = "{:.2f}", prefix: str = "", suffix: str = "", ma_window: int = 30, pr_type: str = 'C'):
    # 1. 無數據防呆機制
    if column not in df.columns:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-desc'>{desc}</div><div style='font-weight:bold; color:#EF4444;'>無數據 (請點左側清除快取)</div></div>", unsafe_allow_html=True)
        return

    valid_data = df[column].dropna()
    if valid_data.empty or len(valid_data) < ma_window:
        st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-desc'>{desc}</div><div style='font-weight:bold; color:#F59E0B;'>數據不足</div></div>", unsafe_allow_html=True)
        return

    # 2. 計算基礎數據與趨勢
    s_period = valid_data.tail(ma_window)
    current_val = s_period.iloc[-1]
    last_date = s_period.index[-1].strftime("%Y-%m-%d")
    avg_val = s_period.mean()
    deviation = current_val - avg_val
    deviation_pct = (deviation / abs(avg_val)) * 100 if avg_val != 0 else 0

    # 3. 🟢 五階動態熱力圖 PR 徽章生成引擎
    def get_pr_badge(pr_v, label):
        if pr_v >= 90: style = "background-color: #991B1B; color: #FFFFFF;" # 深紅 (極端危險)
        elif pr_v >= 80: style = "background-color: #EA580C; color: #FFFFFF;" # 橘紅 (警戒)
        elif pr_v >= 20: style = "background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1;" # 灰白 (常態)
        elif pr_v >= 10: style = "background-color: #D1FAE5; color: #065F46; border: 1px solid #34D399;" # 淺綠 (超跌)
        else: style = "background-color: #064E3B; color: #FFFFFF;" # 深綠 (黃金坑)
        return f"<div style='{style} display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; margin-left: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);'>{label} {pr_v:.0f}</div>"

    # 4. 計算 C-PR (週期) 或 G-PR (雙乖離)
    pr_html = ""
    if len(valid_data) >= 252:
        if pr_type == 'C':
            pr_val = valid_data.rank(pct=True).iloc[-1] * 100
            if column == "Yield_Curve": pr_val = (1.0 - valid_data.rank(pct=True).iloc[-1]) * 100
            pr_html = get_pr_badge(pr_val, "C-PR")
        elif pr_type == 'G':
            # 計算 120 日乖離 PR
            ma120 = valid_data.rolling(window=120).mean()
            dev120 = ((valid_data - ma120) / ma120).dropna()
            if not dev120.empty: pr_html += get_pr_badge(dev120.rank(pct=True).iloc[-1] * 100, "G-120PR")
            # 計算 200 日乖離 PR
            ma200 = valid_data.rolling(window=200).mean()
            dev200 = ((valid_data - ma200) / ma200).dropna()
            if not dev200.empty: pr_html += get_pr_badge(dev200.rank(pct=True).iloc[-1] * 100, "G-200PR")

    # 5. 判斷顏色與趨勢變動文字
    is_up = deviation >= 0
    if invert_color:
        line_color = COLORS['red'] if is_up else COLORS['emerald']
        dev_class = "deviation-negative" if is_up else "deviation-positive"
    else:
        line_color = COLORS['emerald'] if is_up else COLORS['red']
        dev_class = "deviation-positive" if is_up else "deviation-negative"
        
    dev_sign = "+" if is_up else ""
    val_str = f"{prefix}{val_format.format(current_val)}{suffix}"

    # 6. 繪製 Plotly 迷你趨勢圖
    fig = go.Figure()
    if pr_type == 'C':
        # 週期型指標加上均值虛線
        fig.add_trace(go.Scatter(x=[s_period.index[0], s_period.index[-1]], y=[avg_val, avg_val], mode='lines', line=dict(color=COLORS['tech_silver'], width=2, dash='dash'), hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=s_period.index, y=s_period.values, mode='lines', line=dict(color=line_color, width=3), hovertemplate='%{x|%m-%d}: %{y:.2f}<extra></extra>'))
    fig.update_layout(height=70, margin=dict(l=0, r=0, t=5, b=0), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis=dict(visible=False, showgrid=False), yaxis=dict(visible=False, showgrid=False))

    dev_label = f"<span style='color: {COLORS['ink']}; font-size: 0.85rem; font-weight: 600;'>近期趨勢</span>" if pr_type == 'C' else f"<span class='{dev_class}'>{dev_sign}{deviation_pct:.1f}% (距月線)</span>"

    # 7. 🟢 最終 HTML 渲染 (置中大字體版) - 確保只有一次輸出！
    st.markdown(f"""
        <div class="metric-card">
            <div style="position: absolute; top: 12px; right: 12px; display: flex; gap: 2px;">{pr_html}</div>
            <div>
                <div class="metric-title">{title}</div>
                <div class="metric-desc">{desc}</div>
            </div>
            <div>
                <div class="metric-value">{val_str}</div>
                <div class="dev-label">{dev_label}</div>
            </div>
            <div class="metric-date">資料日期: {last_date}</div>
        </div>
    """, unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, key=f"chart_{column}_{pr_type}")

    
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
    details.append(f"{'🟢' if qqq_score>=0 else '🔴'} 科技股距月線 {qqq_dev:+.1f}% ({qqq_score:+.0f}分)")

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
    st.markdown("當以下 **4 個條件滿足 3 個以上**時，代表市場系統性風險解除，是散戶跟著華爾街大戶『重新大舉買入股票與長債』的歷史級時刻。")
    
    brent_val = df['Brent'].dropna().iloc[-1] if 'Brent' in df.columns else 100.0
    cpi_yoy = df['CPI_YoY'].dropna().iloc[-1] if 'CPI_YoY' in df.columns else 5.0
    dgs10_val = df['DGS10'].dropna().iloc[-1] if 'DGS10' in df.columns else 5.0
    dgs30_val = df['DGS30'].dropna().iloc[-1] if 'DGS30' in df.columns else 5.0  
    
    dgs2_val = df['DGS2'].dropna().iloc[-1] if 'DGS2' in df.columns else 5.0
    iorb_val = df['IORB'].dropna().iloc[-1] if 'IORB' in df.columns else 5.0
    rate_cut_priced_in = dgs2_val < (iorb_val - 0.25)
    
    cond_1 = brent_val < 90.0
    cond_2 = cpi_yoy < 2.5
    cond_3 = (dgs10_val < 4.3) and (dgs30_val < 4.5) 
    cond_4 = rate_cut_priced_in
    
    signals_met = sum([cond_1, cond_2, cond_3, cond_4])
    
    # 卡片 1, 2 的產生器 (取消縮排避免跑版)
    def get_card_html(title, current_val, target, is_met, desc, unit=""):
        bg_color = "#ECFDF5" if is_met else "#F8FAFC"
        border_color = "#10B981" if is_met else "#CBD5E1"
        icon = "✅" if is_met else "⏳"
        status_color = "#059669" if is_met else "#64748B"
        return f"""<div style="background-color: {bg_color}; border: 2px solid {border_color}; border-radius: 8px; padding: 15px; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: space-between;"><div><div style="font-size: 1.5rem; margin-bottom: 5px;">{icon}</div><div style="font-weight: 900; color: #0F172A; font-size: 1.05rem;">{title}</div><div style="margin-top: 8px; font-size: 0.9rem; color: #475569;">目標: <span style="font-weight:bold;">{target}</span></div><div style="margin-top: 5px; font-size: 1.2rem; font-weight: 900; color: {status_color};">當前: {current_val:.2f}{unit}</div></div><div style="margin-top: 12px; font-size: 0.8rem; color: #334155; text-align: left; background-color: rgba(255,255,255,0.6); padding: 8px; border-radius: 6px;"><b>💡：</b>{desc}</div></div>"""

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(get_card_html("1. 原油解除通膨警報", brent_val, "< $90", cond_1, "油價是萬物齊漲的源頭。跌破90元代表通膨惡夢結束，聯準會才有底氣印鈔票救市。", "$"), unsafe_allow_html=True)
    with c2: st.markdown(get_card_html("2. 廣義 CPI 實質降溫", cpi_yoy, "< 2.5%", cond_2, "官方物價漲幅達標。代表聯準會不再需要用『高利率』來壓榨實體經濟，資金準備解放。", "%"), unsafe_allow_html=True)
    
    with c3: 
        bg_color_3 = "#ECFDF5" if cond_3 else "#F8FAFC"
        border_color_3 = "#10B981" if cond_3 else "#CBD5E1"
        color_10y = "#059669" if dgs10_val < 4.3 else "#DC2626"
        color_30y = "#059669" if dgs30_val < 4.5 else "#DC2626"
        # 必須把 HTML 壓縮寫在同一行，不可有空白行或四格以上的縮排，防範 Streamlit 的 Code Block 判定
        html_3 = f"""<div style="background-color: {bg_color_3}; border: 2px solid {border_color_3}; border-radius: 8px; padding: 15px; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: space-between;"><div><div style="font-size: 1.5rem; margin-bottom: 5px;">{'✅' if cond_3 else '⏳'}</div><div style="font-weight: 900; color: #0F172A; font-size: 1.05rem;">3. 長天期美債解除警報</div><div style="margin-top: 8px; font-size: 0.85rem; color: #475569;">目標: <span style="font-weight:bold;">10年<4.3% 且 30年<4.5%</span></div><div style="display: flex; justify-content: space-between; margin-top: 10px; gap: 5px;"><div style="flex: 1; background: #ffffff; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;"><div style="font-size: 0.75rem; color: #64748B; font-weight: bold;">10年期 (企業估值)</div><div style="font-size: 1.1rem; font-weight: 900; color: {color_10y};">{dgs10_val:.2f}%</div><div style="font-size: 0.7rem; color: #DC2626; margin-top: 4px;">&gt;4.5% 科技股殺估值</div><div style="font-size: 0.7rem; color: #059669;">&lt;4.3% 資金進場擴張</div></div><div style="flex: 1; background: #ffffff; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;"><div style="font-size: 0.75rem; color: #64748B; font-weight: bold;">30年期 (房貸/通膨)</div><div style="font-size: 1.1rem; font-weight: 900; color: {color_30y};">{dgs30_val:.2f}%</div><div style="font-size: 0.7rem; color: #DC2626; margin-top: 4px;">&gt;5.0% 長線資金撤退</div><div style="font-size: 0.7rem; color: #059669;">&lt;4.5% 實體經濟復甦</div></div></div></div><div style="margin-top: 12px; font-size: 0.8rem; color: #334155; text-align: left; background-color: rgba(255,255,255,0.6); padding: 8px; border-radius: 6px;"><b>💡：</b>兩大長期利率同時回落，代表「高息壓榨」結束，股市與房市的長線大戶才會真正放心拿錢出來買進。</div></div>"""
        st.markdown(html_3, unsafe_allow_html=True)

    with c4: 
        status_text = "已定價降息" if cond_4 else "緊縮震盪中"
        bg_color_4 = "#ECFDF5" if cond_4 else "#F8FAFC"
        border_color_4 = "#10B981" if cond_4 else "#CBD5E1"
        color_2y = "#059669" if cond_4 else "#0F172A"
        html_4 = f"""<div style="background-color: {bg_color_4}; border: 2px solid {border_color_4}; border-radius: 8px; padding: 15px; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: space-between;"><div><div style="font-size: 1.5rem; margin-bottom: 5px;">{'✅' if cond_4 else '⏳'}</div><div style="font-weight: 900; color: #0F172A; font-size: 1.05rem;">4. 聯準會降息定價</div><div style="margin-top: 8px; font-size: 0.85rem; color: #475569;">標準: <span style="font-weight:bold;">2年債 &lt; 基準利率1碼</span></div><div style="display: flex; justify-content: space-between; margin-top: 10px; gap: 5px;"><div style="flex: 1; background: #ffffff; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;"><div style="font-size: 0.75rem; color: #64748B; font-weight: bold;">2年期國債 (市場)</div><div style="font-size: 1.1rem; font-weight: 900; color: {color_2y};">{dgs2_val:.2f}%</div></div><div style="flex: 1; background: #ffffff; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;"><div style="font-size: 0.75rem; color: #64748B; font-weight: bold;">基準利率 (官方)</div><div style="font-size: 1.1rem; font-weight: 900; color: #0F172A;">{iorb_val:.2f}%</div></div></div></div><div style="margin-top: 12px; font-size: 0.8rem; color: #334155; text-align: left; background-color: rgba(255,255,255,0.6); padding: 8px; border-radius: 6px;"><b>💡：</b>2年期國債代表「聰明錢的預期」。當它大幅低於現在官方規定的利息，代表市場拿真金白銀在賭「水龍頭即將打開了」。</div></div>"""
        st.markdown(html_4, unsafe_allow_html=True)
        
    if signals_met >= 3:
        st.success(f"🔥 歷史級長線買點浮現！目前已滿足 {signals_met}/4 項機構抄底條件，可開始將資金大舉轉向風險資產 (股票/長債)。")
    else:
        st.warning(f"⚠️ 目前僅滿足 {signals_met}/4 項條件。尚未出現明確多頭訊號，資金應保持防禦姿態 (現金/短債/月配息)，耐心等待。")

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
    
    # === 原有資料預處理 (確保 CPI 年增率正確計算) ===

    # === 新增：半導體賽道擁擠度計算 ===
    if 'SMH' in df.columns:
        # 計算 200 日乖離率 (FOMO 指標)
        df['SMH_MA200'] = df['SMH'].rolling(window=200).mean()
        df['SMH_Dev_200D'] = ((df['SMH'] - df['SMH_MA200']) / df['SMH_MA200']) * 100
        
        # 計算 SMH/SPY 相對強度 (資金虹吸指標)
        if 'SPY' in df.columns:
            df['SMH_SPY_Ratio'] = df['SMH'] / df['SPY']
            df['SMH_SPY_Ratio_MA60'] = df['SMH_SPY_Ratio'].rolling(window=60).mean()
            # 短期(季線)相對強度乖離
            df['SMH_Relative_Strength'] = ((df['SMH_SPY_Ratio'] - df['SMH_SPY_Ratio_MA60']) / df['SMH_SPY_Ratio_MA60']) * 100

    if 'CPI' in df.columns: 
        df['CPI_YoY'] = (df['CPI'] / df['CPI'].shift(252) - 1) * 100 
    if 'Core_PCE' in df.columns: 
        df['Core_PCE_YoY'] = (df['Core_PCE'] / df['Core_PCE'].shift(252) - 1) * 100
        
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

    if 'Unemployment_Rate' in df.columns:
        df['U3_MA3'] = df['Unemployment_Rate'].rolling(window=63).mean()
        df['U3_MA3_min12'] = df['U3_MA3'].rolling(window=252).min()
        df['Sahm_Indicator'] = df['U3_MA3'] - df['U3_MA3_min12']

    df = df.ffill().bfill()

    import os
    api_key = os.environ.get("GEMINI_API_KEY") or (st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None)
    
    # 初始化 session_state
    if "ai_data" not in st.session_state:
        st.session_state.ai_data = {}

    # 🛑 加入手動安全鎖：只有按鈕被按下時才呼叫 AI
    if not st.session_state.ai_data and api_key:
        st.info("💡 數據已載入完畢。點擊下方按鈕召喚荷莉大師進行今日總經解盤！(此舉將保護你的免費 API 額度)")
        if st.button("🤖 生成今日 AI 深度解盤", use_container_width=True):
            with st.spinner("🤖 正在結合五大防線與最新新聞進行深度解讀，請稍候..."):
                st.session_state.ai_data = generate_ai_summary(df, api_key)
                st.rerun() # 跑完自動重整畫面

    ai_result = st.session_state.ai_data
    macro_insight = ai_result.get("macro_phase_insight", "💡 尚未取得 AI 總經觀測，請點擊上方按鈕解讀。")

    render_taiwan_health_score(df, macro_insight) 
    render_ai_broadcast(ai_result) 
    render_bottom_fishing_signals(df)  

    st.divider()
    st.subheader("⚡ 戰術雷達：高頻微觀與籌碼動能 (一週變盤雷達)")
    t1, t2, t3 = st.columns(3)
    with t1: draw_trend_card(df, "USDTWD_ROC_5D", "台幣 5 日動能 (外資生死線)", "外資匯出匯入的超短期溫度計。<br><span style='color:#0284C7;'><b>💡：</b>大於 +0.5% (台幣急貶) 代表外資正在瘋狂撤資逃命；小於 -0.5% 代表熱錢湧入台灣準備炒股。</span>", invert_color=True, suffix="%", ma_window=20, pr_type='C')
    with t2: draw_trend_card(df, "HY_Spread_Chg_5D", "垃圾債利差 5 日變化", "華爾街銀行借錢意願的短期指標。<br><span style='color:#0284C7;'><b>💡：</b>數字大於0 (正數) 代表銀行在雨天收傘，體質差的公司借不到錢，股市隨時有連環爆雷風險。</span>", invert_color=True, suffix="%", ma_window=20, pr_type='C')
    with t3: draw_trend_card(df, "VIX_Dev_20D", "VIX 距月線乖離 (情緒偏斜)", "短期恐慌與貪婪的極端值。<br><span style='color:#0284C7;'><b>💡：</b>大於 +15% 代表市場嚇壞了(通常是短線買點)；小於 -15% 代表大家過度樂觀，準備要被割韭菜了。</span>", invert_color=True, suffix="%", ma_window=20, pr_type='C')
    
    st.divider()
    st.subheader("🔥 賽道擁擠度與泡沫雷達 (半導體過熱警報)")
    c1, c2 = st.columns(2)
    with c1: 
        draw_trend_card(
            df, "SMH_Dev_200D", "半導體 200 日乖離 (散戶 FOMO 指標)", 
            "衡量晶片股是否漲到脫離基本面。<br><span style='color:#0284C7;'><b>💡：</b>當乖離率大於 +30% (線圖飆高)，代表散戶已經陷入 FOMO 瘋狂追高，隨時可能觸發『達康泡沫』等級的殺盤；小於 -15% 才是長線無腦買點。</span>", 
            invert_color=True, suffix="%", ma_window=60, pr_type='G'
        )
    with c2: 
        draw_trend_card(
            df, "SMH_Relative_Strength", "半導體資金虹急度 (SMH/SPY 相對強度)", 
            "衡量半導體是否吸乾了全市場的錢。<br><span style='color:#0284C7;'><b>💡：</b>當這個數值急速飆破 +10%，代表全市場的錢像被『黑洞』吸走一樣只炒半導體。這是不健康的單腳跳，通常是大戶準備『獲利了結、資金撤退』的最後警告。</span>", 
            invert_color=True, suffix="%", ma_window=60, pr_type='G'
        )

    st.divider()
    st.subheader("🛡️ 第一道防線：美股大盤與板塊")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "SPY", "標普500 (SPY)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>美國 500 大企業加權。<br><b>📊 閾值：</b>長線必向上。G-120PR > 90 中期過熱，G-200PR > 90 歷史泡沫。<br><b>⚔️ 連動：</b>全球資產定價基準，跌破月線代表大資金撤退。</div>", ma_window=30, pr_type='G')
    with c2: draw_trend_card(df, "QQQ", "那斯達克100 (QQQ)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>科技巨頭(含蘋果、輝達)。<br><b>📊 閾值：</b>波動較 SPY 大，PR > 90 極度擁擠。<br><b>⚔️ 連動：</b>台股電子股的親大哥，它破底台灣必遭外資無情提款。</div>", ma_window=30, pr_type='G')
    with c3: draw_trend_card(df, "IWM", "羅素2000 (IWM)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>美國中小型企業。<br><b>📊 閾值：</b>受內需與利率影響最深。<br><b>⚔️ 連動：</b>大盤創高但它破底，代表高利率正壓垮底層經濟，屬於嚴重背離警報。</div>", ma_window=30, pr_type='G')
    with c4: draw_trend_card(df, "XLP", "必需消費板塊 (XLP)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>民生必需品(牙膏/衛生紙)。<br><b>📊 閾值：</b>平時漲幅小。<br><b>⚔️ 連動：</b>科技股大跌但它逆勢漲，代表大戶沒把錢抽離股市，而是躲來這裡保命。</div>", ma_window=30, pr_type='G')

    st.divider()
    st.subheader("🇹🇼 補充防線：台股風向球")
    c1, c2, c3 = st.columns(3)
    with c1: draw_trend_card(df, "SOX", "費城半導體 (SOX)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>全球半導體霸主集合。<br><b>📊 閾值：</b>景氣循環極強，G-200PR < 10 必是歷史大底。<br><b>⚔️ 連動：</b>與台積電連動度 >90%，直接決定台股明天的漲跌生死。</div>", ma_window=30, pr_type='G')
    with c2: draw_trend_card(df, "Copper", "銅博士期貨", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>全球工業金屬之母。<br><b>📊 閾值：</b>長線受基建與 AI 需求推動。<br><b>⚔️ 連動：</b>銅價大漲代表實體經濟(拉貨)熱絡；暴跌暗示全球需求萎縮。</div>", prefix="$", ma_window=30, pr_type='G')
    with c3: draw_trend_card(df, "USDTWD", "美元兌台幣", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>台幣匯率。<br><b>📊 閾值：</b>C-PR > 80 台幣嚴重貶值。<br><b>⚔️ 連動：</b>向上(貶值)代表外資賣台股匯出；向下(升值)代表熱錢湧入買台股。</div>", invert_color=True, ma_window=30, pr_type='C')

    st.divider()
    st.subheader("💣 第二/三道防線：黑天鵝與匯率戰")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "VIX", "恐慌指數 (VIX)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>選擇權市場避險保費。<br><b>📊 閾值：</b>>20 警戒，>30 股災，<13 提防樂極生悲。<br><b>⚔️ 連動：</b>與 SPY 完全反向，C-PR > 95 是極端恐慌的逆勢買點。</div>", invert_color=True, ma_window=120, pr_type='C')
    with c2: draw_trend_card(df, "High_Yield_Spread", "垃圾債利差", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>垃圾債減去無風險美債利息。<br><b>📊 閾值：</b>>5% 亮黃燈，>8% 企業連環倒閉。<br><b>⚔️ 連動：</b>飆高代表銀行抽銀根，股市必暴跌，應立刻轉入現金與長債。</div>", invert_color=True, suffix="%", ma_window=120, pr_type='C')
    with c3: draw_trend_card(df, "DXY", "美元指數 (DXY)", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>美元對全球貨幣強弱。<br><b>📊 閾值：</b>>105 強勢美元警報。<br><b>⚔️ 連動：</b>強美元會吸乾新興市場(台灣)資金引發雙殺；弱美元則有利資金外溢推升亞股。</div>", invert_color=True, ma_window=120, pr_type='C')
    with c4: draw_trend_card(df, "DGS30", "30年期美債殖利率", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>長線通膨與成長預期。<br><b>📊 閾值：</b>飆破 4.5% 會引發拋售潮。<br><b>⚔️ 連動：</b>無風險利率太香，大資金會賣股買債，對科技股估值產生毀滅性打擊。</div>", invert_color=True, suffix="%", pr_type='C')

    st.divider()
    st.subheader("🛢️ 第四道防線：通膨與泡沫")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "Brent", "布倫特原油", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>全球油價基準。<br><b>📊 閾值：</b>突破 $90 即點燃通膨死灰。<br><b>⚔️ 連動：</b>油價居高不下，聯準會就不敢降息，股市資金動能將嚴重受限。</div>", invert_color=True, prefix="$", ma_window=120, pr_type='C') 
    with c2: draw_trend_card(df, "Gold", "黃金期貨", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>終極保命資產。<br><b>📊 閾值：</b>創歷史新高代表信用體系動搖。<br><b>⚔️ 連動：</b>股跌金漲=躲避災難；股金齊漲=市場預期鈔票將大幅貶值(通膨)。</div>", prefix="$", ma_window=120, pr_type='G')
    with c3: draw_trend_card(df, "CPI_YoY", "廣義 CPI 年增率", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>官方整體物價漲幅。<br><b>📊 閾值：</b>聯準會 KPI 是 2%，大於 3% 即拉警報。<br><b>⚔️ 連動：</b>只要卡在 3% 以上，降息預期就會落空，長天期美債將面臨拋售壓力。</div>", invert_color=True, suffix="%", pr_type='C') 
    with c4: draw_trend_card(df, "Buffett", "巴菲特指標", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>美股總市值 / 實體 GDP。<br><b>📊 閾值：</b>>150% 代表嚴重超漲。<br><b>⚔️ 連動：</b>雖不代表馬上崩盤，但處於深紅極端位階時，應嚴格控制股票倉位水位。</div>", invert_color=True, suffix="%", pr_type='C')

    st.divider()
    st.subheader("🏦 第五道防線：聯準會底層水箱")
    c1, c2, c3, c4 = st.columns(4)
    with c1: draw_trend_card(df, "Reserves_T", "銀行準備金", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>聯準會放在銀行的閒錢。<br><b>📊 閾值：</b>低於 3 兆美元代表活水枯竭。<br><b>⚔️ 連動：</b>錢越多股市越漲；下滑趨勢確立時，美股將面臨估值下修壓力。</div>", suffix=" 兆", ma_window=120, pr_type='C')
    with c2: draw_trend_card(df, "RRP_T", "ON RRP 備用金", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>停泊在聯準會的超額現金。<br><b>📊 閾值：</b>歸零即失去流動性保護傘。<br><b>⚔️ 連動：</b>減少代表錢被拿去買美債了；若數字見底，股市震盪將變得極度劇烈。</div>", suffix=" 兆", pr_type='C')
    with c3: draw_trend_card(df, "Liquidity_Spread", "短期資金吃緊度", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>SOFR 減去 基準利率。<br><b>📊 閾值：</b>翻正(>0)即爆發資金荒。<br><b>⚔️ 連動：</b>代表華爾街連借錢過夜都有困難，隨時爆發如 2019 年的雷曼級機構破產危機。</div>", invert_color=True, suffix="%", pr_type='C')
    with c4: draw_trend_card(df, "Yield_Curve", "長短債利差", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>10年期 減 2年期國債利率。<br><b>📊 閾值：</b>常態為正，倒掛(負數)是警報。<br><b>⚔️ 連動：</b>真正恐怖的是「解除倒掛、由負翻正」的那一刻，通常宣告實質大股災到來。</div>", suffix="%", pr_type='C')

    st.divider()
    st.subheader("🏭 終極防線：實體經濟衰退雷達")
    c1, c2, c3 = st.columns(3)
    with c1: draw_trend_card(df, "Unemployment_Rate", "美國失業率", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>勞動市場健康度。<br><b>📊 閾值：</b>形成明顯上升趨勢即不妙。<br><b>⚔️ 連動：</b>一旦狂飆，代表民眾無力消費，此時就算降息也救不回獲利衰退的殺盤。</div>", invert_color=True, suffix="%", pr_type='C')
    with c2: draw_trend_card(df, "Sahm_Indicator", "薩姆衰退指標", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>失業率3個月均值與前低比較。<br><b>📊 閾值：</b>> 0.5% 即宣告 100% 衰退。<br><b>⚔️ 連動：</b>史上最神準警報。一旦觸發，代表經濟陷入硬著陸，風險資產將遭遇拋售。</div>", invert_color=True, suffix="%", pr_type='C')
    with c3: draw_trend_card(df, "Core_PCE_YoY", "核心 PCE 年增率", "<div style='font-size:0.8rem; line-height:1.5;'><b>🧮 公式：</b>扣除能源食物的真實通膨。<br><b>📊 閾值：</b>黏性極強，降至 2% 才安全。<br><b>⚔️ 連動：</b>聯準會決策的唯一核心，此數值不降，大資金就不敢定價寬鬆週期。</div>", invert_color=True, suffix="%", pr_type='C')

if __name__ == "__main__":
    main()