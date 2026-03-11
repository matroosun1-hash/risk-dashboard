"""
데이터 수집 모듈
yfinance를 사용하여 필요한 모든 시장 데이터를 수집합니다.

yfinance 최신 버전은 multi-download 시 MultiIndex 컬럼을 반환합니다.
이 모듈은 두 가지 컬럼 구조를 모두 처리합니다:
  - (Price, Ticker) 형태
  - (Ticker, Price) 형태  (group_by="ticker" 사용 시)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


# 필요한 모든 티커 목록
TICKERS = {
    # 시장 지수
    "market": ["SPY", "QQQ", "IWM", "RSP"],
    # 변동성
    "volatility": ["^VIX", "^VIX3M", "^VIX9D"],
    # 채권/금리
    "bond": ["^TNX", "^IRX", "TLT", "SHY", "IEF"],
    # 크레딧 스프레드
    "credit": ["HYG", "LQD"],
    # 달러
    "dollar": ["UUP", "DX-Y.NYB"],
    # 원자재/에너지 (Oil 등)
    "commodity": ["CL=F", "DBC", "USO"],
    # 섹터 ETF (로테이션 쌍)
    "sector": ["VUG", "VTV", "XLK", "XLP", "XLY", "XLU"],
    # 선행지표
    "leading": ["GLD", "BTC-USD", "SMH"],
    # 방어자산
    "defense": ["WMT", "BRK-B", "PG", "JNJ", "SCHD"],
}


def get_all_tickers() -> list[str]:
    """모든 카테고리의 티커를 하나의 리스트로 반환합니다."""
    all_tickers = []
    for category_tickers in TICKERS.values():
        all_tickers.extend(category_tickers)
    return list(set(all_tickers))  # 중복 제거


def _extract_close_from_multiindex(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """
    yfinance MultiIndex DataFrame에서 각 티커의 Close 가격을 추출합니다.
    
    yfinance 버전에 따라 MultiIndex 구조가 다를 수 있으므로
    두 가지 형태를 모두 시도합니다.
    """
    close_dict = {}
    
    if data.columns.nlevels == 1:
        # 단일 티커 — 컬럼이 ['Close', 'High', 'Low', 'Open', 'Volume']
        if "Close" in data.columns:
            # 단일 티커일 때는 ticker 이름을 알 수 없으므로 호출자가 처리
            return data[["Close"]]
        return pd.DataFrame()
    
    # MultiIndex인 경우
    level0_values = data.columns.get_level_values(0).unique().tolist()
    price_cols = {"Close", "Open", "High", "Low", "Volume"}
    
    if level0_values[0] in price_cols or set(level0_values) & price_cols:
        # 구조: (Price, Ticker) — 예: data["Close"]["SPY"]
        if "Close" in level0_values:
            close_data = data["Close"]
            if isinstance(close_data, pd.Series):
                # 단일 티커
                close_dict[tickers[0]] = close_data
            else:
                for ticker in tickers:
                    if ticker in close_data.columns:
                        series = close_data[ticker].dropna()
                        if not series.empty:
                            close_dict[ticker] = series
    else:
        # 구조: (Ticker, Price) — 예: data["SPY"]["Close"]
        for ticker in tickers:
            try:
                if ticker in level0_values:
                    ticker_data = data[ticker]
                    if "Close" in ticker_data.columns:
                        series = ticker_data["Close"].dropna()
                        if not series.empty:
                            close_dict[ticker] = series
            except (KeyError, TypeError):
                pass
    
    if close_dict:
        return pd.DataFrame(close_dict)
    return pd.DataFrame()


def fetch_market_data(
    tickers: list[str] | None = None,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    yfinance로 시장 데이터를 수집하고 종가 DataFrame을 직접 반환합니다.

    Args:
        tickers: 수집할 티커 리스트. None이면 전체 수집.
        period: 데이터 기간 (예: "1y", "6mo", "2y")
        interval: 데이터 간격 (예: "1d", "1wk")

    Returns:
        날짜 x 티커 형태의 종가 DataFrame.
    """
    if tickers is None:
        tickers = get_all_tickers()

    print(f"📊 {len(tickers)}개 티커 데이터 수집 중...")

    close_df = pd.DataFrame()

    # 방법 1: 전체 한 번에 다운로드
    try:
        data = yf.download(
            tickers,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if not data.empty:
            if len(tickers) == 1:
                # 단일 티커
                if "Close" in data.columns:
                    close_df = pd.DataFrame({tickers[0]: data["Close"]})
                elif data.columns.nlevels > 1:
                    close_df = _extract_close_from_multiindex(data, tickers)
            else:
                close_df = _extract_close_from_multiindex(data, tickers)

    except Exception as e:
        print(f"  ❌ 다중 다운로드 실패: {e}")

    # 방법 2: 누락된 티커는 개별 다운로드로 보완
    downloaded = set(close_df.columns.tolist()) if not close_df.empty else set()
    missing = [t for t in tickers if t not in downloaded]

    if missing:
        print(f"  🔄 {len(missing)}개 티커 개별 다운로드 중: {missing}")
        for ticker in missing:
            try:
                df = yf.download(
                    ticker,
                    period=period,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
                if not df.empty:
                    if "Close" in df.columns:
                        series = df["Close"].dropna()
                        if not series.empty:
                            close_df[ticker] = series
                    elif df.columns.nlevels > 1:
                        # 단일 티커인데 MultiIndex인 경우
                        extracted = _extract_close_from_multiindex(df, [ticker])
                        if ticker in extracted.columns:
                            close_df[ticker] = extracted[ticker]
            except Exception as ex:
                print(f"  ❌ {ticker}: {ex}")

    close_df = close_df.sort_index()
    
    # 최종 확인
    final_count = len(close_df.columns)
    print(f"✅ {final_count}/{len(tickers)}개 티커 수집 완료")
    
    if final_count < len(tickers):
        still_missing = [t for t in tickers if t not in close_df.columns]
        if still_missing:
            print(f"  ⚠️ 미수집 티커: {still_missing}")

    return close_df


def get_close_prices(market_data) -> pd.DataFrame:
    """
    fetch_market_data()의 반환값에서 종가 DataFrame을 추출합니다.
    
    호환성을 위해 유지: fetch_market_data()가 이미 종가 DataFrame을 반환하므로
    그대로 통과시킵니다. 이전 버전(dict 반환) 호환도 지원합니다.
    """
    if isinstance(market_data, pd.DataFrame):
        return market_data
    
    # 이전 버전 호환: dict[str, DataFrame] 형태
    if isinstance(market_data, dict):
        close_dict = {}
        for ticker, df in market_data.items():
            if isinstance(df, pd.DataFrame) and "Close" in df.columns:
                close_dict[ticker] = df["Close"]
            elif isinstance(df, pd.Series):
                close_dict[ticker] = df
        return pd.DataFrame(close_dict).sort_index()
    
    return pd.DataFrame()


def get_returns(close_prices: pd.DataFrame, period: int = 1) -> pd.DataFrame:
    """종가 DataFrame에서 N일 수익률을 계산합니다."""
    return close_prices.pct_change(periods=period)


def get_ratio(close_prices: pd.DataFrame, num: str, den: str) -> pd.Series:
    """
    두 자산의 가격 비율을 계산합니다 (NaN이 아닌 행만 사용).
    """
    if num in close_prices.columns and den in close_prices.columns:
        ratio = close_prices[num] / close_prices[den]
        return ratio.dropna()
    else:
        missing = []
        if num not in close_prices.columns:
            missing.append(num)
        if den not in close_prices.columns:
            missing.append(den)
        raise ValueError(f"티커 없음: {missing}")


def get_sma(series: pd.Series, period: int) -> pd.Series:
    """단순 이동평균을 계산합니다 (NaN을 건너뛰어 계산)."""
    clean = series.dropna()
    return clean.rolling(window=period, min_periods=period).mean()


def get_rolling_std(series: pd.Series, period: int) -> pd.Series:
    """롤링 표준편차를 계산합니다."""
    clean = series.dropna()
    return clean.rolling(window=period, min_periods=period).std()


if __name__ == "__main__":
    # 간단 테스트
    close = fetch_market_data(tickers=["SPY", "QQQ", "^VIX"], period="3mo")
    print(f"\n수집된 티커: {close.columns.tolist()}")
    print(f"\n최근 5일 종가:")
    print(close.tail())
