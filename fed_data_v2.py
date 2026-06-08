import os
import json
import requests
import pandas as pd
import time
import streamlit as st
from google import genai
from google.genai import types
import yfinance as yf
import feedparser
from datetime import datetime, timedelta

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
    "DGS30": ("DGS30", False),                # 🟢 新增：30年期美債
    "DGS10": ("DGS10", False),                  
    "DGS2": ("DGS2", False),
    "CPI": ("CPIAUCSL", False),               # 🟢 新增：廣義 CPI (通膨之母)
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
    "WTI": "CL=F", "Brent": "BZ=F", "Gold": "GC=F", "Copper": "HG=F" # 🟢 新增：布倫特原油 (BZ=F)
}

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

# ==========================================
# 2. 資料抓取模組
# ==========================================
def _fetch_single_series(col_name, series_id, in_billions, observation_start, key):
    try:
        r = requests.get(
            FRED_OBS_URL,
            params={"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "asc", "observation_start": observation_start},
            timeout=15,
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
    except Exception as e:
        print(f"⚠️ FRED API 抓取失敗 [{col_name}]: {e}")
        return None

def fetch_fed_data(api_key=None, years_back=10):
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        try: key = st.secrets["FRED_API_KEY"]
        except: pass
    if not key: 
        return pd.DataFrame()

    observation_start = (datetime.now() - timedelta(days=years_back * 365)).strftime("%Y-%m-%d")
    dfs = []
    
    for col, (sid, in_b) in FRED_SERIES.items():
        res = _fetch_single_series(col, sid, in_b, observation_start, key)
        if res is not None:
            dfs.append(res)
        time.sleep(0.6)
            
    fred_df = pd.concat(dfs, axis=1).sort_index() if dfs else pd.DataFrame()
    if not fred_df.empty: fred_df = fred_df.ffill().bfill()

    try:
        yf_data = pd.DataFrame()
        for nick_name, official_ticker in YF_TICKERS.items():
            try:
                single_yf = yf.download(official_ticker, period=f"{years_back}y", progress=False)
                if not single_yf.empty and 'Close' in single_yf.columns:
                    s = single_yf['Close']
                    if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
                    yf_data[nick_name] = s
            except Exception:
                pass

        if not yf_data.empty:
            yf_data.index = yf_data.index.tz_localize(None) 
            yf_data = yf_data.ffill().bfill() 
            if 'SOX' in yf_data.columns and 'SPY' in yf_data.columns:
                sox_spy_ratio = (yf_data['SOX'] / yf_data['SPY']).dropna()
                if len(sox_spy_ratio) > 120:
                    ma120_ratio = sox_spy_ratio.rolling(window=120).mean()
                    dev_ratio = ((sox_spy_ratio - ma120_ratio) / ma120_ratio).dropna()
                    if not dev_ratio.empty:
                        yf_data['Semi_Relative_Strength_RawDev'] = dev_ratio

            if not fred_df.empty:
                final_df = fred_df.join(yf_data, how='outer').sort_index()
                return final_df.ffill().bfill()
            return yf_data.ffill().bfill()
    except Exception:
        return fred_df.ffill().bfill() if not fred_df.empty else pd.DataFrame()
    return fred_df.ffill().bfill()

def fetch_financial_news(limit=5):
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
    except Exception:
        pass
    return "[今日國際新聞] 暫時無法取得，請純依據量化數據解盤。\n"

# ==========================================
# 3. 量化核心：PR 值與【三大體制動態機率】引擎
# ==========================================
def calculate_pr_matrix(df):
    pr = {}
    if len(df) < 252: return pr
    df_clean = df.ffill().bfill()

    # 1. 預先計算高頻戰術變數 (為了算機率)
    if 'USDTWD' in df_clean.columns: df_clean['USDTWD_ROC_5D'] = df_clean['USDTWD'].pct_change(periods=5) * 100
    if 'High_Yield_Spread' in df_clean.columns: df_clean['HY_Spread_Chg_5D'] = df_clean['High_Yield_Spread'].diff(periods=5)
    if 'VIX' in df_clean.columns:
        vix_ma20 = df_clean['VIX'].rolling(window=20).mean()
        df_clean['VIX_Dev_20D'] = ((df_clean['VIX'] - vix_ma20) / vix_ma20) * 100

    usdtwd_roc_5d = df_clean['USDTWD_ROC_5D'].dropna().iloc[-1] if 'USDTWD_ROC_5D' in df_clean.columns else 0.0
    hy_chg_5d = df_clean['HY_Spread_Chg_5D'].dropna().iloc[-1] if 'HY_Spread_Chg_5D' in df_clean.columns else 0.0
    vix_dev_20d = df_clean['VIX_Dev_20D'].dropna().iloc[-1] if 'VIX_Dev_20D' in df_clean.columns else 0.0

    # 2. 結合高頻雷達，計算真實市場體制機率
    tail_risk = 5.0
    if hy_chg_5d > 0.1: tail_risk += 15.0  # 抽銀根大扣分
    if usdtwd_roc_5d > 0.5: tail_risk += 10.0 # 外資大逃亡
    if vix_dev_20d > 15.0: tail_risk += 10.0 # 極度恐慌
    
    high_vol = 25.0
    if abs(vix_dev_20d) > 10.0: high_vol += 15.0
    if abs(usdtwd_roc_5d) > 0.2: high_vol += 15.0
    
    tail_risk = min(max(tail_risk, 2.0), 95.0)
    high_vol = min(max(high_vol, 5.0), 100.0 - tail_risk - 5.0)
    low_vol = 100.0 - tail_risk - high_vol

    pr['Forecast_Prob_Low_Vol'] = round(low_vol, 1)
    pr['Forecast_Prob_High_Vol'] = round(high_vol, 1)
    pr['Forecast_Prob_Black_Swan'] = round(tail_risk, 1)

    # 3. 其他基礎 PR 計算
    cyclical_cols = ['VIX', 'High_Yield_Spread', 'DXY', 'USDTWD']
    for col in cyclical_cols:
        if col in df_clean.columns:
            s = df_clean[col].dropna()
            if not s.empty: pr[f"{col}_PR"] = s.rank(pct=True).iloc[-1] * 100
    
    if 'DGS10' in df_clean.columns and 'DGS2' in df_clean.columns:
        spread = (df_clean['DGS10'] - df_clean['DGS2']).dropna()
        if not spread.empty: pr['Yield_Curve_Risk_PR'] = (1.0 - spread.rank(pct=True).iloc[-1]) * 100

    growth_cols = ['SPY', 'QQQ', 'IWM', 'SOX', 'WTI', 'Copper', 'TAIEX']
    for col in growth_cols:
        if col in df_clean.columns:
            s = df_clean[col].dropna()
            if len(s) > 120:
                ma120 = s.rolling(window=120).mean()
                dev = ((s - ma120) / ma120).dropna()
                if not dev.empty: pr[f"{col}_DevPR"] = dev.rank(pct=True).iloc[-1] * 100

    if 'Semi_Relative_Strength_RawDev' in df_clean.columns:
        s_dev = df_clean['Semi_Relative_Strength_RawDev'].dropna()
        if not s_dev.empty: pr['Semi_Relative_Strength_PR'] = s_dev.rank(pct=True).iloc[-1] * 100

    if 'TAIEX' in df_clean.columns and 'VIX' in df_clean.columns:
        vix_5d_pct = (df_clean['VIX'].iloc[-1] / 100) * (5 / 252) ** 0.5
        beta = 1.3 + (pr.get('Semi_Relative_Strength_PR', 50) - 50) / 100
        pr['Forecast_5D_TAIEX_High'] = df_clean['TAIEX'].iloc[-1] * (1 + (vix_5d_pct * beta))
        pr['Forecast_5D_TAIEX_Low'] = df_clean['TAIEX'].iloc[-1] * (1 - (vix_5d_pct * beta))

    if 'Buffett' in df_clean.columns: 
        buffett = df_clean['Buffett'].dropna()
        if not buffett.empty: pr['Buffett_PR'] = buffett.rank(pct=True).iloc[-1] * 100
    elif 'Wilshire_5000' in df_clean.columns and 'US_GDP' in df_clean.columns:
        w5000 = df_clean['Wilshire_5000'].ffill()
        gdp = df_clean['US_GDP'].ffill().bfill()
        buffett = (w5000 / gdp).dropna()
        if not buffett.empty: pr['Buffett_PR'] = buffett.rank(pct=True).iloc[-1] * 100
        
    return pr

# ==========================================
# 4. AI 晨報生成 (帶防護罩版)
# ==========================================
def generate_ai_summary(df, api_key=None):
    df_secure = df.ffill().bfill()
    pr = calculate_pr_matrix(df_secure)
    
    # 🛡️ 終極防線：先把算好的機率存起來，保證絕對不會遺失！
    base_result = {
        "Forecast_Prob_Low_Vol": pr.get('Forecast_Prob_Low_Vol', 60.0),
        "Forecast_Prob_High_Vol": pr.get('Forecast_Prob_High_Vol', 30.0),
        "Forecast_Prob_Black_Swan": pr.get('Forecast_Prob_Black_Swan', 10.0),
        "macro_phase_insight": "尚未取得 AI 總經觀測，請點擊重新解讀或檢查 API。",
        "broadcast": "💡 系統提示：AI 模組連線超時或 API 錯誤。但高頻戰術機率與指標已透過 Python 量化矩陣計算完成，請參考下方數值。"
    }

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        try: key = st.secrets["GEMINI_API_KEY"]
        except: pass
    if not key: 
        base_result["error"] = "請在 Streamlit Secrets 設定 GEMINI_API_KEY"
        return base_result
    
    usdtwd_roc_5d = df_secure['USDTWD_ROC_5D'].dropna().iloc[-1] if 'USDTWD_ROC_5D' in df_secure.columns else 0.0
    hy_chg_5d = df_secure['HY_Spread_Chg_5D'].dropna().iloc[-1] if 'HY_Spread_Chg_5D' in df_secure.columns else 0.0
    vix_dev_20d = df_secure['VIX_Dev_20D'].dropna().iloc[-1] if 'VIX_Dev_20D' in df_secure.columns else 0.0

    data_summary = (
        f"數據日期: {df_secure.index[-1].strftime('%Y-%m-%d')}\n"
        f"- VIX 恐慌指數 PR: {pr.get('VIX_PR', 0):.1f} | 巴菲特指標 PR: {pr.get('Buffett_PR', 50):.1f}\n"
        f"- 外資生死線(台幣5日動能): {usdtwd_roc_5d:+.2f}%\n"
        f"- 信用利差動態(5日變化): {hy_chg_5d:+.2f}%\n"
        f"- 選擇權情緒(VIX乖離): {vix_dev_20d:+.2f}%\n"
    )

    system_prompt_raw = """
    你是一位擁有 30 年經驗的總經量化投資大師。請為穩健型高階半導體產業客戶規劃資產配置。
    【🚨 輸出要求】JSON 的 Value 內【絕對禁止】真實換行符號。
    {
        "macro_phase_insight": "【當前經濟階段與今日驅動】",
        "broadcast": "<h4 style='color:#0044CC; margin-bottom: 5px;'>🏦 總經定調</h4><ul style='line-height: 1.8; margin-top: 0;'><li><b>高頻籌碼與匯率：</b>(解讀台幣5日動能與VIX乖離)</li></ul>",
        "allocation_recommendation": {"twd_cash": 15, "usd_assets": 30, "cashflow": 25, "core_growth": 15, "tactical_hedge": 15},
        "allocation_reasons": {"twd_cash": "保留現金", "usd_assets": "鎖定高息", "cashflow": "00937B 提供被動收入", "core_growth": "采鈺等核心持股", "tactical_hedge": "極小部位短打矽光子/AI強勢股"},
        "market_insights_html": "<div><h4 style='color: #0284C7;'>🔄 未來一週操作劇本</h4><p>(分析高頻指標)</p><h4 style='color: #F59E0B;'>🔥 科技股熱點</h4><p>(帶入 AI、矽光子CPO、CoWoS)</p></div>"
    }
    """

    client = genai.Client(api_key=key)
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=system_prompt_raw + "\n\n" + data_summary,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )
        raw_text = response.text.strip()
        return json.loads(raw_text) if raw_text else {}
    except Exception as e:
        return {"error": f"AI 暫時無法連線，請檢查網路或 API Key 是否正確。({str(e)})"} 