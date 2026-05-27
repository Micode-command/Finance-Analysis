"""
從 FRED 取得聯準會資產負債與利率數據。
包含進階的市場動態分析、白話文解釋與總經健康度評分。
"""
import os
import pandas as pd
import requests
import google.generativeai as genai  
from datetime import datetime, timedelta

# FRED 欄位名稱 -> (series_id, 單位是否為十億需乘 1000 轉百萬)
FRED_SERIES = {
    "Total_Assets": ("WALCL", False),           
    "Treasury_Securities": ("TREAST", False),   
    "MBS": ("WSHOMCB", False),                  
    "ON_RRP": ("RRPONTSYD", True),              
    "Reserve_Balances": ("WRESBAL", False),     
    "TGA_Account": ("WDTGAL", False),           
    "EFFR": ("DFF", False),                     
    "IORB": ("IORB", False),                    
    "SOFR": ("SOFR", False),                    
    "DGS10": ("DGS10", False),                  
    "DGS2": ("DGS2", False),                    
}

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

def fetch_fed_data(api_key: str | None = None, years_back: int = 10) -> pd.DataFrame:
    """抓取過去 10 年的 FRED 數據"""
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        raise ValueError("請設定 FRED API Key：環境變數 FRED_API_KEY")

    observation_start = (datetime.now() - timedelta(days=years_back * 365)).strftime("%Y-%m-%d")
    dfs = []
    
    for col_name, (series_id, in_billions) in FRED_SERIES.items():
        try:
            r = requests.get(
                FRED_OBS_URL,
                params={
                    "series_id": series_id, "api_key": key,
                    "file_type": "json", "sort_order": "asc",
                    "observation_start": observation_start,
                },
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            obs = data.get("observations", [])
            if not obs: continue
            rows = []
            for o in obs:
                if o.get("value") in (".", None, ""): continue
                try: val = float(o["value"])
                except (TypeError, ValueError): continue
                if in_billions: val = val * 1000
                rows.append({"date": o["date"], col_name: val})
            if rows:
                df_one = pd.DataFrame(rows)
                df_one["date"] = pd.to_datetime(df_one["date"])
                df_one = df_one.set_index("date")
                dfs.append(df_one)
        except requests.RequestException:
            continue

    if not dfs: return pd.DataFrame()

    out = dfs[0]
    for d in dfs[1:]:
        out = out.join(d, how="outer")
    
    # 保持不做 ffill，以確保計算 delta 時能抓到真實交易日
    out = out.sort_index()
    return out

def get_last_two(df: pd.DataFrame, col: str):
    """取得該欄位最後兩個「非空值」的真實數據，包含防呆機制"""
    # === 新增防呆：如果 FRED 剛好沒傳回這個欄位，直接回傳空值，避免當機 ===
    if col not in df.columns:
        return None, None
        
    s = df[col].dropna()
    if len(s) >= 2: return s.iloc[-1], s.iloc[-2]
    if len(s) == 1: return s.iloc[-1], None
    return None, None

def analyze_market_dynamics(data: pd.DataFrame) -> dict:
    if data.empty or len(data) < 2: return {}
    health_score = 100

    # 1. 流動性壓力 (SOFR vs IORB)
    liquidity_stress = {}
    sofr_latest, sofr_prev = get_last_two(data, 'SOFR')
    iorb_latest, iorb_prev = get_last_two(data, 'IORB')
    
    if all(v is not None for v in [sofr_latest, iorb_latest, sofr_prev, iorb_prev]):
        spread_latest = sofr_latest - iorb_latest
        if spread_latest > 0.02:
            label, color, health_score = '🔴 流動性緊縮 (資金吃緊)', '#DC2626', health_score - 40
            insight = f'SOFR-IORB 利差達 {spread_latest:.3f}%。短期融資成本顯著高於準備金利率。'
            layman = '銀行之間互相借錢的利息變貴了！代表市場上「現金很缺」，大家都在搶錢。'
        elif spread_latest > -0.05:
            label, color, health_score = '🟡 流動性警戒 (正常波動)', '#FBBF24', health_score - 15
            insight = f'SOFR-IORB 利差 {spread_latest:.3f}%。處於正常區間，需持續監控。'
            layman = '市場上的資金供需目前剛剛好，沒有特別缺錢，也沒有錢太多氾濫的狀況。'
        else:
            label, color = '🟢 流動性充裕 (資金氾濫)', '#10B981'
            insight = f'SOFR-IORB 利差 {spread_latest:.3f}%。流動性極度充裕。'
            layman = '銀行手上的現金多到滿出來，借錢成本極低，熱錢容易湧入股市等風險資產。'

        liquidity_stress = {'label': label, 'color': color, 'insight': insight, 'layman_explanation': layman}

    # 2. 緩衝池枯竭度 (ON RRP)
    buffer_depletion = {}
    rrp_latest, rrp_prev = get_last_two(data, 'ON_RRP')
    ast_latest, ast_prev = get_last_two(data, 'Total_Assets')
    
    if all(v is not None and v > 0 for v in [rrp_latest, ast_latest, rrp_prev, ast_prev]):
        ratio_latest = (rrp_latest / ast_latest) * 100
        if ratio_latest < 1:
            label, color, health_score = '🔴 緩衝池乾涸', '#DC2626', health_score - 30
            insight = f'ON RRP 佔比降至 {ratio_latest:.2f}%。流動性緩衝耗盡。'
            layman = '市場資金的「停車場」空了！這代表用來緩衝金融震盪的閒置資金已經枯竭。'
        elif ratio_latest <= 5:
            label, color, health_score = '🟡 緩衝池低水位', '#FBBF24', health_score - 10
            insight = f'ON RRP 佔比 {ratio_latest:.2f}%。流動性緩衝處於低水位。'
            layman = '市場備用資金的水位正在下降中，雖然還沒見底，但需要提高警覺。'
        else:
            label, color = '🟢 緩衝池充足', '#10B981'
            insight = f'ON RRP 佔比 {ratio_latest:.2f}%。流動性緩衝充足。'
            layman = '市場的備用資金還很夠，如果發生突發狀況，有足夠的錢可以拿出來救火。'

        buffer_depletion = {'label': label, 'color': color, 'insight': insight, 'layman_explanation': layman}

    # 3. QT 縮表強度
    qt_intensity = {}
    s_ast = data['Total_Assets'].dropna()
    if len(s_ast) > 30:
        a_lat = s_ast.iloc[-1]
        mo_ago_lat = s_ast.iloc[-30]
        chg_latest = ((a_lat - mo_ago_lat) / mo_ago_lat) * 100
        
        if chg_latest < -0.5:
            label, color, health_score = '🔴 激進縮表 (強力抽銀根)', '#DC2626', health_score - 30
            insight = f'總資產月變動率 {chg_latest:.2f}%。激進 QT 快速收緊金融條件。'
            layman = '聯準會正在大力把市場上的錢收回來（抽水），這會讓投資市場的動能熄火。'
        elif chg_latest < 0:
            label, color, health_score = '🟡 溫和縮表 (緩慢抽水)', '#FBBF24', health_score - 10
            insight = f'總資產月變動率 {chg_latest:.2f}%。溫和 QT 進行中。'
            layman = '聯準會正在慢慢地把錢收回來，力道不大，市場暫時還能適應。'
        else:
            label, color = '🟢 暫停或擴表 (重新注水)', '#10B981'
            insight = f'總資產月變動率 {chg_latest:.2f}%。Fed 停止收水，支撐流動性。'
            layman = '聯準會停止收回資金，甚至可能開始印鈔票了！這對股市通常是打了一劑強心針。'

        qt_intensity = {'label': label, 'color': color, 'insight': insight, 'layman_explanation': layman}

    # 4. 殖利率曲線倒掛 (10Y vs 2Y)
    yield_curve = {}
    dgs10_latest, dgs10_prev = get_last_two(data, 'DGS10')
    dgs2_latest, dgs2_prev = get_last_two(data, 'DGS2')

    if all(v is not None for v in [dgs10_latest, dgs2_latest, dgs10_prev, dgs2_prev]):
        spread_latest = dgs10_latest - dgs2_latest
        if spread_latest < 0:
            label, color, health_score = '🔴 嚴重倒掛 (衰退警報)', '#DC2626', health_score - 20
            insight = f'10Y-2Y 利差 {spread_latest:.3f}%。長短天期倒掛，市場預期經濟衰退。'
            layman = '銀行的「短期定存」利息竟然比「長期定存」還高！代表大家對未來的經濟很悲觀，是經濟衰退的強烈預警。'
        elif spread_latest < 0.5:
            label, color = '🟡 趨於平坦 (動能減弱)', '#FBBF24'
            insight = f'10Y-2Y 利差 {spread_latest:.3f}%。曲線平坦化，動能減弱。'
            layman = '長期與短期的利息差不多，代表市場對未來經濟沒有太大的信心，處於觀望狀態。'
        else:
            label, color = '🟢 曲線陡峭 (經濟擴張)', '#10B981'
            insight = f'10Y-2Y 利差 {spread_latest:.3f}%。反映健康的經濟擴張預期。'
            layman = '長期利息高於短期利息，這是最正常的狀態！代表大家願意把錢長期投資出去。'

        yield_curve = {'label': label, 'color': color, 'insight': insight, 'layman_explanation': layman}

    health_score = max(0, min(100, health_score))
    if health_score >= 80:
        status, desc = "🟢 資金派對中 (適合積極佈局)", "目前聯準會資金活水充沛，金融體系健康。"
    elif health_score >= 50:
        status, desc = "🟡 資金穩定 (中性看待)", "資金面不構成大阻力也沒有大推力。"
    else:
        status, desc = "🔴 資金退潮 (建議保守，增加現金水位)", "流動性枯竭，系統性風險增加，建議保留現金。"

    return {
        'liquidity_stress': liquidity_stress,
        'buffer_depletion': buffer_depletion,
        'qt_intensity': qt_intensity,
        'yield_curve': yield_curve,
        'macro_health': {'score': health_score, 'status': status, 'description': desc}
    }

def get_sparkline_data(data: pd.DataFrame, column: str, periods: int = 365) -> pd.DataFrame:
    if data.empty or column not in data.columns: return pd.DataFrame()
    return data[[column]].ffill().tail(periods)

def calculate_delta(data: pd.DataFrame, column: str) -> tuple:
    if data.empty or column not in data.columns:
        return None, None, None, "—"
    valid_data = data[column].dropna()
    if len(valid_data) < 2: 
        return (valid_data.iloc[-1] if len(valid_data) > 0 else None), None, None, "—"
    
    current = valid_data.iloc[-1]
    previous = valid_data.iloc[-2]
    return current, previous, current - previous, None
import pandas as pd

def generate_ai_summary(df: pd.DataFrame, api_key: str = None) -> dict:
    """
    使用 Google Gemini 針對當前數據生成一段給平民老百姓看的總經晨報。
    保留了完整的 9 大未來宏觀變數與華爾街老手人設，並採用 JSON 格式輸出以節省 Token。
    """
    import google.generativeai as genai
    import os
    import json
    
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"error": "⚠️ 請設定 GEMINI_API_KEY 以啟用 AI 智慧解讀功能。"}

    # 1. 精準提取最新與前一日數據
    df_clean = df.ffill() 
    latest = df_clean.iloc[-1]
    prev = df_clean.iloc[-2]
    
    # 計算關鍵數字
    reserves = latest.get('Reserve_Balances', 0) / 1e6
    reserves_delta = (latest.get('Reserve_Balances', 0) - prev.get('Reserve_Balances', 0)) / 1e6
    on_rrp = latest.get('ON_RRP', 0) / 1e6
    tga = latest.get('TGA_Account', 0) / 1e6
    sofr_iorb_spread = latest.get('SOFR', 0) - latest.get('IORB', 0)
    yield_spread = latest.get('DGS10', 0) - latest.get('DGS2', 0)

    # ==========================================
    # 🔥 完整保留：未來宏觀變數
    # ==========================================
    macro_events = """
    1. [2026/03/18] Fed FOMC 利率決策與 SEP 發布：最新經濟預測摘要 (SEP) 的點陣圖將確立 2026 上半年降息路徑，直接重塑全球無風險利率與 S&P 500 估值折現率。
    2. [2026/03/19] ECB 歐洲央行貨幣政策會議：決定歐元區三大關鍵利率，其決策將牽動歐美利差變化及全球資本在美元與歐元間的流動方向。
    3. [2026/04/15] 美國企業與個人繳稅截止日 (Tax Day)：預計將有數千億美元稅款流入財政部一般帳戶 (TGA)，導致銀行準備金等量收縮，將顯著壓抑春季市場流動性。
    4. [2026/06/17] Fed FOMC 年中利率決策與 SEP 發布：作為年中貨幣政策轉折點，聯邦資金利率的調整將決定下半年全球美元流動性與企業融資成本水位。
    5. [2026/12/31] 北美雲端巨頭與 TSMC AI 資本支出 (Capex) 結算：六大巨頭預計投入逾 5,000 億美元，台積電亦達 520-560 億美元，龐大資金將實質轉化為 AI 半導體與矽光子 (Silicon Photonics) 供應鏈的營收動能。
    6. [2026/05/06] 美國財政部季度發債計畫 (QRA)：發布下半年長短期公債發行比例，此籌資結構將直接決定 TGA 帳戶餘額回補速度與 10 年期美債期限溢價 (Term Premium)。
    7. [2026/06/16-17] BOJ 日本央行貨幣政策會議與 JGB 縮減評估：日銀將針對日本國債 (JGB) 購買縮減計畫進行關鍵期中評估，若決議加速縮表或升息，將驅使身為美國最大債權國的日本資本回流，抽離美債與美股市場流動性。
    8. [2026/11/03] 美國期中選舉 (US Midterm Elections)：國會兩院控制權的潛在更迭將決定未來聯邦財政赤字規模與稅改政策延續性，選前市場避險情緒通常會系統性降低風險資產的流動性。
    9. [2026/12/31] ECB PEPP 與 APP 全面縮表 (QT) 效應發酵：歐洲央行已全面停止疫情緊急購債計畫 (PEPP) 再投資，2026 年預估每月穩定縮減資產，持續產生結構性的歐元區流動性收緊效應，並推升歐美利差波動。
    """

    # 2. 整理成強迫 AI 閱讀的硬數據與大事件表
    data_summary = f"""
    【今日真實數據 (你必須基於以下數字解盤)】
    - 日期: {latest.name.strftime('%Y-%m-%d')}
    - 銀行準備金 (活水): {reserves:.2f} 兆美元 (較前次變動: {reserves_delta:+.2f} 兆)
    - ON RRP (備用緩衝): {on_rrp:.2f} 兆美元
    - TGA (政府金庫): {tga:.2f} 兆美元
    - 短期資金利率: SOFR {latest.get('SOFR', 0):.3f}%, IORB {latest.get('IORB', 0):.3f}%
    - SOFR-IORB 利差 (短期流動性壓力): {sofr_iorb_spread:.3f}% (若 > 0.02% 代表緊縮)
    - 10Y-2Y 公債利差 (經濟預期): {yield_spread:.3f}% (若 < 0 代表倒掛/衰退警報)
    
    【近期重大宏觀變數 (你必須將以下事件融入未來的風險預判)】
    {macro_events}
    """
    
    # 3. 升級版：保留人設，但強制 JSON 結構輸出
    system_prompt = """
    你是一位擁有 30 年華爾街操盤經驗的「總經老手」，現在退隱當教授。你的任務是把今天聯準會最新的「真實數據」以及「未來的世界大事」，精準翻譯給在台灣的普通老百姓了解，給出投資的策略。

    【🚨 嚴格禁忌指令】
    1. 絕對不准說「假想」、「假設」、「舉例來說」或「數據迷航」。
    2. 你必須直接引用下方【今日真實數據】中的具體數字來佐證你的觀點。
    3. 必須結合【近期重大宏觀變數】來做未來推演。

    【📝 JSON 輸出結構要求】
    你必須輸出為純 JSON 格式，包含以下三個 key (請確保是合法的 JSON)：
    
    1. "broadcast": 包含你完整解盤的字串。請使用 HTML 標籤 (如 <br>, <b>) 進行換行與粗體排版。內容必須包含三段：
       【老手看盤】：一句話鐵口直斷目前資金環境，並引用1~2個真實數據解釋。
       【未來風暴預警】：結合近期重大宏觀變數，告訴台灣老百姓未來1~2個月對現金流與股市的震盪影響。
       【平民生存指南】：給出在台灣生存的具體資產配置建議(如哪種ETF、債券、高股息或保留現金)。
       
    2. "rates_insight": 針對目前的 SOFR 與公債殖利率狀態，給出一段 50 字以內，犀利一針見血的「利率市場洞察」。
    
    3. "macro_insight": 針對目前三大水箱 (準備金/ON RRP/TGA) 的資金流動性，給出一段 50 字以內，犀利一針見血的「資金動態點評」。
    """

    try:
        genai.configure(api_key=key)
        # 關鍵設定：強制 AI 將回應格式化為 JSON
        model = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config={"response_mime_type": "application/json"}
        ) 
        response = model.generate_content(system_prompt + "\n\n" + data_summary)
        
        # 將 AI 回傳的 JSON 字串轉換為 Python 字典
        return json.loads(response.text)
    except Exception as e:
        return {"error": f"AI 暫時罷工中 ({str(e)})，請檢查 API 狀態或稍後再試。"}