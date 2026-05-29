import os
import json
import requests
import pandas as pd
from google import genai
from google.genai import types
import yfinance as yf
import feedparser  # RSS 新聞解析套件
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
    "WTI": "CL=F", "Gold": "GC=F", "Copper": "HG=F",
    "TAIEX": "^TWII"  # 🔥 新增：台灣加權指數，作為核心預測大盤
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
        yf_data = pd.DataFrame()
        for nick_name, official_ticker in YF_TICKERS.items():
            try:
                single_yf = yf.download(official_ticker, period=f"{years_back}y", progress=False)
                if not single_yf.empty:
                    if 'Close' in single_yf.columns:
                        s = single_yf['Close']
                        if isinstance(s, pd.DataFrame): 
                            s = s.iloc[:, 0]
                        yf_data[nick_name] = s
            except Exception as e_single:
                print(f"⚠️ 抓取單檔 {nick_name} ({official_ticker}) 失敗: {e_single}")

        if not yf_data.empty:
            yf_data.index = yf_data.index.tz_localize(None) 
            
            # 先在純股票環境下算出半導體與大盤的相對乖離，防止時間差
            if 'SOX' in yf_data.columns and 'SPY' in yf_data.columns:
                sox_spy_ratio = (yf_data['SOX'] / yf_data['SPY']).dropna()
                if len(sox_spy_ratio) > 120:
                    ma120_ratio = sox_spy_ratio.rolling(window=120).mean()
                    dev_ratio = ((sox_spy_ratio - ma120_ratio) / ma120_ratio).dropna()
                    if not dev_ratio.empty:
                        yf_data['Semi_Relative_Strength_RawDev'] = dev_ratio

            # 🛠️ 終極修復點：大合併時使用雙向填充（先 ffill 再 bfill），徹底抹平月底與每日交易的時間空缺
            if not fred_df.empty:
                final_df = fred_df.join(yf_data, how='outer').sort_index()
                return final_df.ffill().bfill()
            return yf_data.ffill().bfill()
            
    except Exception as e:
        print(f"⚠️ 雅虎財經整體模組執行失敗: {e}")
        return fred_df.ffill().bfill()

    return fred_df.ffill().bfill()

# ==========================================
# 2.5 RSS 財經新聞抓取模組
# ==========================================
def fetch_financial_news(limit=5) -> str:
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

    # 🛠️ 確保進入矩陣計算前，整張表最新的一列數據也是填滿的狀態
    df_clean = df.ffill().bfill()

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
                if not dev.empty:
                    pr[f"{col}_DevPR"] = dev.rank(pct=True).iloc[-1] * 100

    if 'Semi_Relative_Strength_RawDev' in df_clean.columns:
        s_dev = df_clean['Semi_Relative_Strength_RawDev'].dropna()
        if not s_dev.empty:
            pr['Semi_Relative_Strength_PR'] = s_dev.rank(pct=True).iloc[-1] * 100

    # === 🚀 核心優化：將預測目標切換為「台灣加權指數 (TAIEX)」 ===
    if 'TAIEX' in df_clean.columns and 'VIX' in df_clean.columns:
        current_taiex = df_clean['TAIEX'].iloc[-1]
        current_vix = df_clean['VIX'].iloc[-1]
        
        # 依據統計學公式，推算未來 5 個交易日台股的波動標準差區間
        five_day_std_dev_pct = (current_vix / 100) * (5 / 252) ** 0.5
        pr['Forecast_5D_TAIEX_High'] = current_taiex * (1 + five_day_std_dev_pct)
        pr['Forecast_5D_TAIEX_Low'] = current_taiex * (1 - five_day_std_dev_pct)
        
    # === 馬可夫變盤暴風雨機率 ===
    if 'VIX_PR' in pr or ('VIX' in df_clean.columns):
        vix_pr_val = pr.get('VIX_PR', df_clean['VIX'].rank(pct=True).iloc[-1] * 100)
        hys_pr_val = pr.get('High_Yield_Spread_PR', 50)
        semi_pr_val = pr.get('Semi_Relative_Strength_PR', 50)
        storm_score = (vix_pr_val * 0.3) + (hys_pr_val * 0.3) + (semi_pr_val * 0.4)
        pr['Forecast_5D_Storm_Probability'] = storm_score

    # 🛠️ 終極修復點：巴菲特指標相除前與相除後均實施強效填充，消滅無數據
    if 'Buffett' in df_clean.columns: 
        buffett = df_clean['Buffett'].ffill().bfill().dropna()
        if not buffett.empty: pr['Buffett_PR'] = buffett.rank(pct=True).iloc[-1] * 100
    elif 'Wilshire_5000' in df_clean.columns and 'US_GDP' in df_clean.columns:
        w5000 = df_clean['Wilshire_5000'].ffill().bfill()
        gdp = df_clean['US_GDP'].ffill().bfill()
        buffett_raw = w5000 / gdp
        buffett = buffett_raw.ffill().bfill().dropna()
        if not buffett.empty: pr['Buffett_PR'] = buffett.rank(pct=True).iloc[-1] * 100
    return pr

# ==========================================
# 4. AI 機構級立體晨報生成 (台股預測完全體版)
# ==========================================
def generate_ai_summary(df: pd.DataFrame, api_key: str = None) -> dict:
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key: return {"error": "請設定 GEMINI_API_KEY"}

    # 確保最後一行也是填充飽滿的
    df_clean = df.ffill().bfill()
    latest = df_clean.iloc[-1]
    pr = calculate_pr_matrix(df_clean)
    
    semi_relative_pr = pr.get('Semi_Relative_Strength_PR', 50.0)
    
    # 提取台股（TAIEX）相關預測參數
    current_taiex_val = df_clean['TAIEX'].iloc[-1] if 'TAIEX' in df_clean.columns else 0
    forecast_high = pr.get('Forecast_5D_TAIEX_High', current_taiex_val * 1.03)
    forecast_low = pr.get('Forecast_5D_TAIEX_Low', current_taiex_val * 0.97)
    storm_prob = pr.get('Forecast_5D_Storm_Probability', 50.0)
    
    liquidity_roc = df_clean['Liquidity_ROC_4W'].dropna().iloc[-1] if 'Liquidity_ROC_4W' in df_clean.columns else 0
    sahm_val = df_clean['Sahm_Indicator'].dropna().iloc[-1] if 'Sahm_Indicator' in df_clean.columns else 0
    pce_yoy = df_clean['Core_PCE_YoY'].dropna().iloc[-1] if 'Core_PCE_YoY' in df_clean.columns else 0
    buffett_pr = pr.get('Buffett_PR', 50)
    
    news_feed = fetch_financial_news(limit=5)
    
    # 安全常規字串拼接，傳遞最新的台股與全球量化參數
    data_summary = (
        f"【今日真實數據與 10 年期 PR 值 (0-100)】\n"
        f"- 數據日期: {latest.name.strftime('%Y-%m-%d')}\n"
        f"- 當前台灣加權指數 (TAIEX) 價格: {current_taiex_val:.2f}\n"
        f"- VIX 恐慌指數 PR: {pr.get('VIX_PR', 0):.1f} | 垃圾債違約利差 PR: {pr.get('High_Yield_Spread_PR', 0):.1f}\n"
        f"- 科技股(QQQ) 乖離PR: {pr.get('QQQ_DevPR', 0):.1f} | 費半(SOX) 乖離PR: {pr.get('SOX_DevPR', 0):.1f}\n"
        f"- 台股加權指數(TAIEX) 乖離PR: {pr.get('TAIEX_DevPR', 0):.1f}\n"
        f"- 半導體/大盤相對強度乖離 PR: {semi_relative_pr:.1f}\n"
        f"- 巴菲特指標 PR: {buffett_pr:.1f}\n"
        f"- 美國淨流動性 4 週變動率 (ROC): {liquidity_roc:.2f}%\n"
        f"- 薩姆規則衰退指標: {sahm_val:.2f}% | 核心 PCE 年增率: {pce_yoy:.2f}%\n\n"
        f"【📊 本大師量化模型——未來一週 (5個交易日) 台灣大盤預測數據】\n"
        f"- 馬可夫狀態轉換：未來一週台股切換至「高波動劇烈洗盤型態」的暴風雨機率: {storm_prob:.1f}%\n"
        f"- 依據波動率公式反推，統計學上未來一週台股加權指數最合理的震盪天花板（高標）: {forecast_high:.2f}\n"
        f"- 依據波動率公式反推，統計學上未來一週台股加權指數最合理的震盪地板（低標）: {forecast_low:.2f}\n\n"
        f"{news_feed}"
    )

    # 系統提示詞（無 f 前綴，100% 免疫大括號語法衝突）
    system_prompt_raw = """
    你是一位擁有 30 年經驗的總經量化投資大師。請為穩健型投資客戶規劃全天候資產配置，並且結合我提供給你的【未來一週台灣大盤預測數據】，嚴密盲測接下來一週內台股大盤可能的變化與走勢。

    【🛡️ 終極動態護盾與配比指令】
    目前薩姆規則：__SAHM__%
    目前巴菲特 PR：__BUFFETT__
    目前淨流動性 ROC：__LIQ__%
    目前半導體相較大盤相對強度 PR：__SEMI__
    
    請依據以下邏輯給出 allocation_recommendation (加總必須為 100)：
    1. ☠️ [實質衰退] (薩姆>0.5)：現金與美債必須 > 70%，股票 < 10%。
    2. 🌋 [末升段泡沫] (巴菲特>85 且 流動性>0)：強制將「核心股票」壓低至 15-20% 以內防禦，「黃金與戰術」可拉高防黑天鵝，剩餘大資金(>60%)強制重壓「月配息」與「外幣/公司債」鎖利。如果 半導體相對強度 PR > 90，請在報告中對台灣半導體權值股高估值風險提出嚴厲警告。
    3. 🔴 [資金退潮] (巴菲特>85 且 流動性<0)：現金與債券 > 80%。
    4. 🟢 [黃金進攻] (巴菲特<40 且 流動性>0)：股票核心與短線戰術 > 60%。

    【🚨 輸出要求 (嚴格防錯格式)】
    - JSON 的 Value 內【絕對禁止】真實換行符號。
    - allocation_reasons：請針對五大板塊，用一句話精準說明該區塊目前的用途是「對衝、攻擊還是防禦什麼事情」。
    - market_insights_html：請使用我提供的 HTML 樣板，針對「未來一週台股趨勢與高低標盲測劇本」、「科技股資金熱點 (如AI、矽光子CPO、先進封裝CoWoS)」、「具體可買標的與操作指南」撰寫深入的實戰分析。

    {
        "macro_phase_insight": "【當前經濟階段與今日驅動】(請點出目前處於擴張、過熱、末升段還是衰退階段？並點出今日台股量化分數主要是受到哪個指標或是新聞影響。)",
        "broadcast": "<h4 style='color:#0044CC; margin-bottom: 5px;'>🏦 總經定調：市場情緒與流動性底牌</h4><ul style='line-height: 1.8; margin-top: 0;'><li><b>實體經濟與通膨：</b>(解讀薩姆規則與 PCE，並結合半導體相對大盤強度分析外資長線留存邏輯)</li><li><b>時事與流動性：</b>(解讀新聞與淨流動性，分析外資短期進出台灣市場的速度)</li></ul><h4 style='color:#0044CC; margin-bottom: 5px;'>⚠️ 結構健健：窄基牛市與黑天鵝雷達</h4><ul style='line-height: 1.8; margin-top: 0;'><li><b>板塊分化與系統風險：</b>(對比台股與美股科技股乖離率落差，解讀巴菲特指標)</li></ul><h4 style='color:#CC0000; margin-bottom: 5px;'>🔮 盲測推演：未來一週台灣大盤走勢預測</h4><ul style='line-height: 1.8; margin-top: 0;'><li><b>台股一週震盪邊界：</b>(務必結合我給你的台股合理震盪高標天花板和低標地板數據，指出未來 5 個交易日加權指數最可能的實戰區間)</li><li><b>台股變盤暴風雨機率：</b>(解讀暴風雨機率機率值，預測本週內台股是會繼續由外資拉抬高檔鈍化，還是高機率出現劇烈洗盤)</li></ul>",
        "allocation_recommendation": {
            "twd_cash": 15, "usd_assets": 30, "cashflow": 25, "core_growth": 15, "tactical_hedge": 15
        },
        "allocation_reasons": {
            "twd_cash": "【絕對防禦】保留現金彈性，應對突發市場崩跌。",
            "usd_assets": "【鎖利防禦】對抗台幣貶值風險，鎖定高息資產。",
            "cashflow": "【震盪護城河】股市高檔震盪時，提供穩定被動收入。",
            "core_growth": "【資本攻擊】吃半導體長期紅利，但因泡沫位階故降低比例。",
            "tactical_hedge": "【黑天鵝防禦/衝刺】黃金對衝地緣風險，極小部位短打矽光子/AI強勢股。"
        },
        "market_insights_html": "<div style='padding: 24px; background-color: #FAFAF9; border: 2px solid #E5E7EB; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'><h3 style='color: #1F2937; margin-top:0; border-bottom: 2px solid #D1D5DB; padding-bottom: 10px; margin-bottom: 16px;'>📰 荷儷專屬：市場大局觀與實戰劇本</h3><div style='margin-bottom: 16px;'><h4 style='color: #0284C7; margin: 0 0 5px 0;'>🔄 未來一週台股趨勢與操作劇本</h4><p style='margin: 0; color: #334155; line-height: 1.6;'>(詳細分析未來 5 天內台股加權指數受到統計學高低標和最新新聞的夾擊，會怎麼走？外資會慢慢撤還是慢慢進？)</p></div><div style='margin-bottom: 16px;'><h4 style='color: #F59E0B; margin: 0 0 5px 0;'>🔥 科技股熱點與產業風向</h4><p style='margin: 0; color: #334155; line-height: 1.6;'>(詳細說明現在資金在炒作科技股的什麼題材？務必帶入 AI、矽光子(CPO)、先進封裝(CoWoS)等前瞻領域的資金動向。)</p></div><div style='margin-bottom: 8px;'><h4 style='color: #10B981; margin: 0 0 5px 0;'>🎯 具體標的與操作指南</h4><p style='margin: 0; color: #334155; line-height: 1.6;'>(具體指出在這個預測局勢下，哪些股票/ETF可以買？分別的作用是什麼？例如：長線佈局核心半導體、特定ETF做防禦、高股息做收租等。)</p></div></div>"
    }
    """
    
    # 執行精準的字串安全代換
    system_prompt = system_prompt_raw.replace("__SAHM__", f"{sahm_val:.2f}")
    system_prompt = system_prompt.replace("__BUFFETT__", f"{buffett_pr:.1f}")
    system_prompt = system_prompt.replace("__LIQ__", f"{liquidity_roc:.2f}")
    system_prompt = system_prompt.replace("__SEMI__", f"{semi_relative_pr:.1f}")
    
    client = genai.Client()
    raw_text = ""
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=system_prompt + "\n\n" + data_summary,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
        )
        raw_text = response.text.strip()
    except Exception as e_pro:
        print(f"⚠️ Pro 模型暫時不可用 ({e_pro})，正在自動切換至 2.5 Flash 備份防線...")
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=system_prompt + "\n\n" + data_summary,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
            )
            raw_text = response.text.strip()
        except Exception as e_flash:
            return {"error": f"大師解盤終極失敗 (Pro & Flash 皆掛點): {e_flash}"}

    try:
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(raw_text, strict=False)
    except Exception as e_json:
        return {"error": f"JSON 解析失敗，錯誤: {e_json}"}