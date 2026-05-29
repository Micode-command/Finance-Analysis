import os
import json
import requests
import pandas as pd
from google import genai
from google.genai import types
import yfinance as yf
import feedparser  # 新增：RSS 新聞解析套件
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==========================================
# 1. 常數與設定
# ==========================================
FRED_SERIES = {
    "Total_Assets": ("WALCL", False),           
    "ON_RRP": ("RRPONTSYD", True),              
    "Reserve_Balances": ("WRESBAL", False),     
    "TGA_Account": ("WDTGAL", False),           
    "IORB": ("IORB", False),                    
    "SOFR": ("SOFR", False),                    
    "DGS10": ("DGS10", False),                  
    "DGS2": ("DGS2", False),
    "Core_PCE": ("PCEPILFE", False),        
    "Unemployment_Rate": ("UNRATE", False), 
    "High_Yield_Spread": ("BAMLH0A0HYM2", False),
    "Wilshire_5000": ("WILL5000PR", False),       
    "US_GDP": ("GDP", False)                      
}

YF_TICKERS = {
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "XLP": "XLP",
    "SOX": "^SOX", "VIX": "^VIX", "DXY": "DX-Y.NYB",
    "USDJPY": "JPY=X", "USDTWD": "TWD=X",
    "WTI": "CL=F", "Gold": "GC=F", "Copper": "HG=F"
}

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

# ==========================================
# 2. 資料抓取模組 (聯準會 + 雅虎財經)
# ==========================================
def _fetch_single_series(col_name: str, series_id: str, in_billions: bool, observation_start: str, key: str) -> pd.DataFrame | None:
    try:
        r = requests.get(
            FRED_OBS_URL,
            params={"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "asc", "observation_start": observation_start},
            timeout=30,
        )
        r.raise_for_status()
        obs = r.json().get("observations", [])
        if not obs: return None

        rows = []
        for o in obs:
            val = o.get("value")
            if val in (".", None, ""): continue
            try: val = float(val)
            except (TypeError, ValueError): continue
            if in_billions: val = val * 1000
            rows.append({"date": o["date"], col_name: val})
            
        if rows:
            df_one = pd.DataFrame(rows)
            df_one["date"] = pd.to_datetime(df_one["date"])
            return df_one.set_index("date")
    except requests.RequestException:
        pass
    return None

def fetch_fed_data(api_key: str | None = None, years_back: int = 10) -> pd.DataFrame:
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key: raise ValueError("請設定 FRED API Key：環境變數 FRED_API_KEY")

    observation_start = (datetime.now() - timedelta(days=years_back * 365)).strftime("%Y-%m-%d")
    dfs = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_fetch_single_series, col, sid, in_b, observation_start, key) for col, (sid, in_b) in FRED_SERIES.items()]
        for future in as_completed(futures):
            res = future.result()
            if res is not None: dfs.append(res)
    fred_df = pd.concat(dfs, axis=1).sort_index() if dfs else pd.DataFrame()

    try:
        tickers_str = " ".join(YF_TICKERS.values())
        yf_data = yf.download(tickers_str, period=f"{years_back}y", progress=False)['Close']
        rename_map = {v: k for k, v in YF_TICKERS.items()}
        yf_data = yf_data.rename(columns=rename_map)
        yf_data.index = yf_data.index.tz_localize(None) 
        
        if not fred_df.empty:
            final_df = fred_df.join(yf_data, how='outer').sort_index()
            return final_df.ffill()
    except Exception as e:
        print(f"⚠️ 雅虎財經資料抓取失敗: {e}")
        return fred_df.ffill()

    return fred_df.ffill()

# ==========================================
# 2.5 新增：RSS 財經新聞抓取模組
# ==========================================
def fetch_financial_news(limit=5) -> str:
    """抓取 CNBC 財經頭條 RSS 作為 AI 解盤的時事背景"""
    # CNBC Finance News RSS (免 API Key，更新即時)
    rss_url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
    news_summary = ""
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            news_summary += "[今日華爾街/全球財經頭條]\n"
            for i, entry in enumerate(feed.entries[:limit]):
                title = entry.get("title", "無標題")
                news_summary += f"{i+1}. {title}\n"
            return news_summary
    except Exception as e:
        print(f"⚠️ RSS 新聞抓取失敗: {e}")
    
    return "[今日國際新聞] 暫時無法取得，請純依據量化數據解盤。\n"

# ==========================================
# 3. 量化核心：十年期 PR 值計算引擎
# ==========================================
def calculate_pr_matrix(df: pd.DataFrame) -> dict:
    pr = {}
    if len(df) < 252: return pr

    cyclical_cols = ['VIX', 'High_Yield_Spread', 'DXY', 'USDTWD']
    for col in cyclical_cols:
        if col in df.columns:
            s = df[col].dropna()
            if not s.empty: pr[f"{col}_PR"] = s.rank(pct=True).iloc[-1] * 100
    
    if 'DGS10' in df.columns and 'DGS2' in df.columns:
        spread = (df['DGS10'] - df['DGS2']).dropna()
        if not spread.empty: pr['Yield_Curve_Risk_PR'] = (1.0 - spread.rank(pct=True).iloc[-1]) * 100

    growth_cols = ['SPY', 'QQQ', 'IWM', 'SOX', 'WTI', 'Copper']
    for col in growth_cols:
        if col in df.columns:
            s = df[col].dropna()
            if len(s) > 120:
                ma120 = s.rolling(window=120).mean()
                dev = ((s - ma120) / ma120).dropna()
                pr[f"{col}_DevPR"] = dev.rank(pct=True).iloc[-1] * 100

    # 模組三：結構估值型 (巴菲特指標 PR)
    if 'Buffett' in df.columns: # 直接吃前端算好的防呆備用數據
        buffett = df['Buffett'].dropna()
        if not buffett.empty: pr['Buffett_PR'] = buffett.rank(pct=True).iloc[-1] * 100
    elif 'Wilshire_5000' in df.columns and 'US_GDP' in df.columns:
        w5000 = df['Wilshire_5000'].ffill()
        gdp = df['US_GDP'].ffill().bfill()
        buffett = (w5000 / gdp).dropna()
        if not buffett.empty: pr['Buffett_PR'] = buffett.rank(pct=True).iloc[-1] * 100
    return pr
# ==========================================
# 4. AI 機構級立體晨報生成 (加入總經趨勢與攻守解析)
# ==========================================
def generate_ai_summary(df: pd.DataFrame, api_key: str = None) -> dict:
    from google import genai
    from google.genai import types
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key: return {"error": "請設定 GEMINI_API_KEY"}

    latest = df.iloc[-1]
    pr = calculate_pr_matrix(df)
    
    liquidity_roc = df['Liquidity_ROC_4W'].dropna().iloc[-1] if 'Liquidity_ROC_4W' in df.columns else 0
    sahm_val = df['Sahm_Indicator'].dropna().iloc[-1] if 'Sahm_Indicator' in df.columns else 0
    pce_yoy = df['Core_PCE_YoY'].dropna().iloc[-1] if 'Core_PCE_YoY' in df.columns else 0
    buffett_pr = pr.get('Buffett_PR', 50)
    
    news_feed = fetch_financial_news(limit=5)
    
    data_summary = f"""
    【今日真實數據與 10 年期 PR 值 (0-100)】
    - 數據日期: {latest.name.strftime('%Y-%m-%d')}
    - VIX 恐慌指數 PR: {pr.get('VIX_PR', 0):.1f} | 垃圾債違約利差 PR: {pr.get('High_Yield_Spread_PR', 0):.1f}
    - 科技股(QQQ) 乖離PR: {pr.get('QQQ_DevPR', 0):.1f} | 費半(SOX) 乖離PR: {pr.get('SOX_DevPR', 0):.1f}
    - 巴菲特指標 PR: {buffett_pr:.1f}
    - 美國淨流動性 4 週變動率 (ROC): {liquidity_roc:.2f}%
    - 薩姆規則衰退指標: {sahm_val:.2f}% | 核心 PCE 年增率: {pce_yoy:.2f}% 
    
    {news_feed}
    """

    system_prompt = f"""
    你是一位擁有 30 年經驗的總經量化基金大師。請為高階半導體產業客戶規劃全天候資產配置。

    【🛡️ 終極動態護盾與配比指令】
    目前薩姆規則：{sahm_val:.2f}%
    目前巴菲特 PR：{buffett_pr:.1f}
    目前淨流動性 ROC：{liquidity_roc:.2f}%
    
    請依據以下邏輯給出 allocation_recommendation (加總必須為 100)：
    1. ☠️ [實質衰退] (薩姆>0.5)：現金與美債必須 > 70%，股票 < 10%。
    2. 🌋 [末升段泡沫] (巴菲特>85 且 流動性>0)：強制將「核心股票」壓低至 15-20% 以內防禦，「黃金與戰術」可拉高防黑天鵝，剩餘大資金(>60%)強制重壓「月配息」與「外幣/公司債」鎖利。
    3. 🔴 [資金退潮] (巴菲特>85 且 流動性<0)：現金與債券 > 80%。
    4. 🟢 [黃金進攻] (巴菲特<40 且 流動性>0)：股票核心與短線戰術 > 60%。

    【🚨 輸出要求 (嚴格防錯格式)】
    - JSON 的 Value 內【絕對禁止】真實換行符號。
    - allocation_reasons：請針對五大板塊，用一句話精準說明該區塊目前的用途是「對衝、攻擊還是防禦什麼事情」。
    - market_insights_html：請使用我提供的 HTML 樣板，針對「當前經濟循環/新聞影響」、「科技股資金熱點 (如AI、矽光子CPO、CoWoS)」、「具體可買標的與用途」撰寫深入的實戰分析。

    {{
        "macro_phase_insight": "【當前經濟階段與今日驅動】(請點出目前處於擴張、過熱、末升段還是衰退階段？並點出今日台股量化分數主要是受到哪個指標影響。)",
        "broadcast": "<h4 style='color:#0044CC; margin-bottom: 5px;'>🏦 總經定調：市場情緒與流動性底牌</h4><ul style='line-height: 1.8; margin-top: 0;'><li><b>實體經濟與通膨：</b>(解讀薩姆規則與 PCE)</li><li><b>時事與流動性：</b>(解讀新聞與淨流動性)</li></ul><h4 style='color:#0044CC; margin-bottom: 5px;'>⚠️ 結構健檢：窄基牛市與黑天鵝雷達</h4><ul style='line-height: 1.8; margin-top: 0;'><li><b>板塊分化與系統風險：</b>(對比乖離率落差與巴菲特指標)</li></ul>",
        "allocation_recommendation": {{
            "twd_cash": 15, "usd_assets": 30, "cashflow": 25, "core_growth": 15, "tactical_hedge": 15
        }},
        "allocation_reasons": {{
            "twd_cash": "【絕對防禦】保留現金彈性，應對突發市場崩跌。",
            "usd_assets": "【鎖利防禦】對抗台幣貶值風險，鎖定 Google 公司債高息。",
            "cashflow": "【震盪護城河】股市高檔震盪時，00937B 提供穩定被動收入。",
            "core_growth": "【資本攻擊】采鈺等核心持股，吃半導體長期紅利，但因泡沫位階故降低比例。",
            "tactical_hedge": "【黑天鵝防禦/衝刺】黃金對衝地緣風險，極小部位短打矽光子/AI強勢股。"
        }},
        "market_insights_html": "<div style='padding: 24px; background-color: #FAFAF9; border: 2px solid #E5E7EB; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'><h3 style='color: #1F2937; margin-top:0; border-bottom: 2px solid #D1D5DB; padding-bottom: 10px; margin-bottom: 16px;'>📰 荷儷專屬：市場大局觀與實戰劇本</h3><div style='margin-bottom: 16px;'><h4 style='color: #0284C7; margin: 0 0 5px 0;'>🔄 經濟循環與新聞事件影響</h4><p style='margin: 0; color: #334155; line-height: 1.6;'>(詳細說明目前處於什麼經濟循環？受到聯準會什麼政策、或今日什麼新聞事件影響？)</p></div><div style='margin-bottom: 16px;'><h4 style='color: #F59E0B; margin: 0 0 5px 0;'>🔥 科技股熱點與產業風向</h4><p style='margin: 0; color: #334155; line-height: 1.6;'>(詳細說明現在資金在炒作科技股的什麼題材？務必帶入 AI、矽光子(CPO)、先進封裝(CoWoS)等前瞻領域的資金動向。)</p></div><div style='margin-bottom: 8px;'><h4 style='color: #10B981; margin: 0 0 5px 0;'>🎯 具體標的與操作指南</h4><p style='margin: 0; color: #334155; line-height: 1.6;'>(具體指出在這個局勢下，哪些股票/ETF可以買？分別的作用是什麼？例如：采鈺做長線、00679B做防禦、00713做收租等。)</p></div></div>"
    }}
    """
    
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=system_prompt + "\n\n" + data_summary,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        raw_text = response.text.strip().strip("`").strip()
        if raw_text.startswith("json"): raw_text = raw_text[4:].strip()
        return json.loads(raw_text, strict=False)
    except Exception as e:
        return {"error": f"大師解盤失敗: {e}"}