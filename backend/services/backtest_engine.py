import pandas as pd
from backtesting import Backtest, Strategy
from services.data_ingestion import fetch_ohlcv

def manual_rsi(prices, n=14):
    """Simple RSI implementation for backtesting."""
    deltas = pd.Series(prices).diff()
    seed = deltas[:n+1]
    up = seed[seed >= 0].sum() / n
    down = -seed[seed < 0].sum() / n
    rs = up / down
    rsi = [100 - 100 / (1 + rs)]
    
    for d in deltas[n+1:]:
        up = (up * (n - 1) + (d if d > 0 else 0)) / n
        down = (down * (n - 1) + (-d if d < 0 else 0)) / n
        rs = up / down
        rsi.append(100 - 100 / (1 + rs))
    return pd.Series(rsi, index=pd.Series(prices).index[n:])

class RSIMACrossStrategy(Strategy):
    """
    Simple RSI + MA Crossover Strategy using manual calculations.
    """
    rsi_window = 14
    ma_window = 50

    def init(self):
        # Calculate indicators manually within the strategy context
        # The I() function in backtesting.py expects a function that returns a series
        self.rsi = self.I(lambda x: pd.Series(x).diff().rolling(self.rsi_window).apply(
            lambda s: 100 - 100/(1 + (s[s>0].sum() / -s[s<0].sum())) if s[s<0].sum() != 0 else 100
        ), self.data.Close)
        
        self.ma = self.I(lambda x: pd.Series(x).rolling(self.ma_window).mean(), self.data.Close)

    def next(self):
        price = self.data.Close[-1]
        
        if not self.position:
            if self.rsi[-1] < 40 and price > self.ma[-1]:
                self.buy()
        else:
            if self.rsi[-1] > 70 or price < self.ma[-1]:
                self.position.close()

def safe_round(val, digits=2):
    try:
        import numpy as np
        if val is None or np.isnan(val) or np.isinf(val):
            return 0.0
        return round(float(val), digits)
    except:
        return 0.0

async def run_backtest(symbol: str, cash: int = 100000, commission: float = 0.002):
    """
    Run backtest for a given symbol with NaN protection.
    """
    df = await fetch_ohlcv(symbol, period="2y", interval="1d")
    
    if df.empty or len(df) < 100:
        raise ValueError(f"Insufficient data for backtesting {symbol}")

    bt = Backtest(df, RSIMACrossStrategy, cash=cash, commission=commission)
    stats = bt.run()
    
    return {
        "symbol": symbol,
        "start": str(stats['Start']),
        "end": str(stats['End']),
        "duration": str(stats['Duration']),
        "exposure_time": safe_round(stats['Exposure Time [%]']),
        "equity_final": safe_round(stats['Equity Final [$]']),
        "equity_peak": safe_round(stats['Equity Peak [$]']),
        "return_percent": safe_round(stats['Return [%]']),
        "buy_hold_return": safe_round(stats['Buy & Hold Return [%]']),
        "sharpe_ratio": safe_round(stats['Sharpe Ratio']),
        "win_rate": safe_round(stats['Win Rate [%]']),
        "max_drawdown": safe_round(stats['Max. Drawdown [%]']),
        "trades_count": int(stats['# Trades']),
    }
