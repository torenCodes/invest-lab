import yfinance as yf
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def fetch_stock_data(ticker, start_date, end_date):
    """
    Fetch stock data with comprehensive error handling
    """
    try:
        if isinstance(ticker, list):
            ticker = ticker[0]
        
        print(f"Fetching data for {ticker}...")
        
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if data.empty:
            print(f"No data found for {ticker}")
            return None
            
        # Handle multi-level columns
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        
        # Validate required columns
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            print(f"Missing required columns: {missing_columns}")
            return None
        
        # Clean data
        data = data.dropna(subset=['Close', 'Volume'])
        
        if len(data) < 50:
            print(f"Insufficient data: {len(data)} rows (need at least 50)")
            return None
            
        print(f"Successfully fetched {len(data)} trading days")
        return data
        
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        return None

def calculate_technical_indicators(data):
    """
    Calculate all technical indicators with error handling
    """
    try:
        print("Calculating technical indicators...")
        
        # === TREND INDICATORS ===
        data['SMA_10'] = ta.sma(data['Close'], length=10)
        data['SMA_20'] = ta.sma(data['Close'], length=20)
        data['SMA_50'] = ta.sma(data['Close'], length=50)
        data['EMA_12'] = ta.ema(data['Close'], length=12)
        data['EMA_26'] = ta.ema(data['Close'], length=26)
        
        # MACD
        macd_data = ta.macd(data['Close'])
        if macd_data is not None and not macd_data.empty:
            # Get column names dynamically
            macd_cols = macd_data.columns.tolist()
            data['MACD'] = macd_data.iloc[:, 0]
            data['MACD_signal'] = macd_data.iloc[:, 1] 
            data['MACD_histogram'] = macd_data.iloc[:, 2]
        else:
            # Create fallback MACD
            data['MACD'] = data['EMA_12'] - data['EMA_26']
            data['MACD_signal'] = ta.ema(data['MACD'], length=9)
            data['MACD_histogram'] = data['MACD'] - data['MACD_signal']
        
        # === MOMENTUM INDICATORS ===
        data['RSI_14'] = ta.rsi(data['Close'], length=14)
        data['RSI_21'] = ta.rsi(data['Close'], length=21)
        
        # Stochastic Oscillator
        stoch_data = ta.stoch(data['High'], data['Low'], data['Close'])
        if stoch_data is not None and not stoch_data.empty:
            data['Stoch_K'] = stoch_data.iloc[:, 0]
            data['Stoch_D'] = stoch_data.iloc[:, 1]
        else:
            # Simple stochastic fallback
            data['Stoch_K'] = ((data['Close'] - data['Low'].rolling(14).min()) / 
                              (data['High'].rolling(14).max() - data['Low'].rolling(14).min())) * 100
            data['Stoch_D'] = data['Stoch_K'].rolling(3).mean()
        
        # Rate of Change
        data['ROC_10'] = ta.roc(data['Close'], length=10) * 100
        data['ROC_20'] = ta.roc(data['Close'], length=20) * 100
        
        # === VOLATILITY INDICATORS ===
        
        # Bollinger Bands
        bb_data = ta.bbands(data['Close'], length=20, std=2)
        if bb_data is not None and not bb_data.empty:
            bb_columns = bb_data.columns.tolist()
            # Find the correct column names
            lower_col = next((col for col in bb_columns if 'BBL' in col or 'lower' in col.lower()), None)
            middle_col = next((col for col in bb_columns if 'BBM' in col or 'middle' in col.lower()), None)  
            upper_col = next((col for col in bb_columns if 'BBU' in col or 'upper' in col.lower()), None)
            
            if all([lower_col, middle_col, upper_col]):
                data['BB_lower'] = bb_data[lower_col]
                data['BB_middle'] = bb_data[middle_col]
                data['BB_upper'] = bb_data[upper_col]
            else:
                # Fallback BB calculation
                sma_20 = data['Close'].rolling(20).mean()
                std_20 = data['Close'].rolling(20).std()
                data['BB_middle'] = sma_20
                data['BB_upper'] = sma_20 + (2 * std_20)
                data['BB_lower'] = sma_20 - (2 * std_20)
        else:
            # Manual BB calculation
            sma_20 = data['Close'].rolling(20).mean()
            std_20 = data['Close'].rolling(20).std()
            data['BB_middle'] = sma_20
            data['BB_upper'] = sma_20 + (2 * std_20)
            data['BB_lower'] = sma_20 - (2 * std_20)
        
        # BB Width and %B
        data['BB_width'] = ((data['BB_upper'] - data['BB_lower']) / data['BB_middle']) * 100
        data['BB_percent'] = ((data['Close'] - data['BB_lower']) / (data['BB_upper'] - data['BB_lower'])) * 100
        
        # Average True Range
        data['ATR'] = ta.atr(data['High'], data['Low'], data['Close'], length=14)
        if data['ATR'].isna().all():
            # Manual ATR calculation
            high_low = data['High'] - data['Low']
            high_close = np.abs(data['High'] - data['Close'].shift())
            low_close = np.abs(data['Low'] - data['Close'].shift())
            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            data['ATR'] = true_range.rolling(14).mean()
        
        # === VOLUME INDICATORS ===
        data['Volume_MA_10'] = data['Volume'].rolling(window=10).mean()
        data['Volume_MA_20'] = data['Volume'].rolling(window=20).mean()
        data['Volume_MA_50'] = data['Volume'].rolling(window=50).mean()
        
        # Volume Rate of Change
        data['Volume_ROC'] = ((data['Volume'] / data['Volume'].shift(10)) - 1) * 100
        
        # On Balance Volume
        data['OBV'] = ta.obv(data['Close'], data['Volume'])
        if data['OBV'].isna().all():
            # Manual OBV calculation
            price_change = data['Close'].diff()
            obv_values = []
            obv = 0
            for i, change in enumerate(price_change):
                if pd.isna(change):
                    obv_values.append(obv)
                elif change > 0:
                    obv += data['Volume'].iloc[i]
                    obv_values.append(obv)
                elif change < 0:
                    obv -= data['Volume'].iloc[i]
                    obv_values.append(obv)
                else:
                    obv_values.append(obv)
            data['OBV'] = obv_values
        
        # Custom Volume Price Trend (since ta.vpt might not exist)
        price_change_pct = data['Close'].pct_change()
        volume_price_trend = (price_change_pct * data['Volume']).cumsum()
        data['VPT'] = volume_price_trend
        
        # Accumulation/Distribution Line
        data['AD'] = ta.ad(data['High'], data['Low'], data['Close'], data['Volume'])
        if data['AD'].isna().all():
            # Manual A/D Line calculation
            money_flow_multiplier = ((data['Close'] - data['Low']) - (data['High'] - data['Close'])) / (data['High'] - data['Low'])
            money_flow_volume = money_flow_multiplier * data['Volume']
            data['AD'] = money_flow_volume.cumsum()
        
        # === PRICE ACTION INDICATORS ===
        
        # Recent highs and lows
        data['High_20'] = data['High'].rolling(window=20).max()
        data['Low_20'] = data['Low'].rolling(window=20).min()
        data['Price_position'] = ((data['Close'] - data['Low_20']) / (data['High_20'] - data['Low_20'])) * 100
        
        # Volatility measurements
        data['Price_volatility'] = data['Close'].pct_change().rolling(window=10).std() * np.sqrt(252) * 100
        data['Volatility_percentile'] = data['Price_volatility'].rolling(window=50).rank(pct=True) * 100
        
        # Gap detection
        data['Gap_up'] = (data['Open'] > data['High'].shift(1)) & (data['Volume'] > data['Volume_MA_20'])
        data['Gap_down'] = (data['Open'] < data['Low'].shift(1)) & (data['Volume'] > data['Volume_MA_20'])
        
        # === RELATIVE STRENGTH vs SPY ===
        try:
            spy_data = yf.download('SPY', start=data.index[0], end=data.index[-1], progress=False)
            if not spy_data.empty:
                if isinstance(spy_data.columns, pd.MultiIndex):
                    spy_data.columns = spy_data.columns.droplevel(1)
                
                # Align dates
                common_dates = data.index.intersection(spy_data.index)
                if len(common_dates) > 20:
                    stock_returns = data.loc[common_dates, 'Close'].pct_change().rolling(20).mean()
                    spy_returns = spy_data.loc[common_dates, 'Close'].pct_change().rolling(20).mean()
                    relative_strength = (stock_returns / spy_returns).fillna(1)
                    data['Relative_Strength'] = relative_strength.reindex(data.index, method='ffill').fillna(1)
                else:
                    data['Relative_Strength'] = 1
            else:
                data['Relative_Strength'] = 1
        except Exception as e:
            print(f"Could not calculate relative strength: {e}")
            data['Relative_Strength'] = 1
        
        # Clean up NaN values
        data = data.dropna()
        
        print(f"Technical indicators calculated successfully. {len(data)} rows remaining.")
        return data
        
    except Exception as e:
        print(f"Error calculating indicators: {str(e)}")
        return None

def detect_breakout_patterns(data):
    """
    Detect various breakout patterns
    """
    try:
        print("Detecting breakout patterns...")
        
        # === CORE BREAKOUT CONDITIONS ===
        
        # Price breakout above Bollinger Band
        price_breakout = data['Close'] > data['BB_upper']
        
        # Volume surge conditions
        volume_surge_basic = data['Volume'] > 1.5 * data['Volume_MA_20']
        volume_surge_strong = (data['Volume'] > 2.0 * data['Volume_MA_20']) & (data['Volume_ROC'] > 30)
        
        # Momentum conditions
        momentum_positive = (
            (data['RSI_14'] > 50) & (data['RSI_14'] < 85) &
            (data['MACD'] > data['MACD_signal']) &
            (data['ROC_10'] > 1)
        )
        
        momentum_strong = (
            (data['RSI_14'] > 55) & (data['RSI_14'] < 80) &
            (data['MACD'] > data['MACD_signal']) &
            (data['MACD_histogram'] > data['MACD_histogram'].shift(1)) &
            (data['ROC_10'] > 3)
        )
        
        # === QUALITY FILTERS ===
        
        # Trend alignment (bull market conditions)
        uptrend_strong = (
            (data['Close'] > data['SMA_10']) &
            (data['SMA_10'] > data['SMA_20']) &
            (data['SMA_20'] > data['SMA_50'])
        )
        
        uptrend_basic = (data['Close'] > data['SMA_20'])
        
        # Position in trading range
        high_in_range = data['Price_position'] > 75
        mid_to_high_range = data['Price_position'] > 60
        
        # Low volatility (consolidation) context
        low_volatility = data['Volatility_percentile'] < 25
        moderate_volatility = data['Volatility_percentile'] < 50
        
        # Relative strength
        outperforming_market = data['Relative_Strength'] > 1.1
        
        # === BREAKOUT SIGNAL TYPES ===
        
        # 1. Basic Breakout
        data['Breakout_Basic'] = price_breakout & volume_surge_basic & momentum_positive
        
        # 2. Quality Breakout 
        data['Breakout_Quality'] = (
            price_breakout & volume_surge_basic & momentum_strong & 
            uptrend_basic & mid_to_high_range
        )
        
        # 3. Premium Breakout (highest quality)
        data['Breakout_Premium'] = (
            price_breakout & volume_surge_strong & momentum_strong & 
            uptrend_strong & high_in_range & outperforming_market
        )
        
        # 4. Consolidation Breakout (from tight ranges)
        data['Breakout_Consolidation'] = (
            price_breakout & volume_surge_basic & momentum_positive & 
            low_volatility & mid_to_high_range
        )
        
        # 5. Momentum Breakout (strong momentum + volume)
        data['Breakout_Momentum'] = (
            price_breakout & volume_surge_strong & momentum_strong
        )
        
        # 6. Gap Breakout
        data['Breakout_Gap'] = (
            data['Gap_up'] & momentum_positive & 
            (data['Volume'] > 2.0 * data['Volume_MA_20'])
        )
        
        # === PATTERN-SPECIFIC BREAKOUTS ===
        
        # Flag pattern (consolidation after strong move)
        recent_strong_move = data['ROC_20'].shift(5) > 15
        recent_tight_range = (
            (data['High'].rolling(5).max() / data['Low'].rolling(5).min() - 1) < 0.06
        ).shift(1)
        
        data['Breakout_Flag'] = (
            price_breakout & volume_surge_basic & momentum_positive &
            recent_strong_move & recent_tight_range
        )
        
        return data
        
    except Exception as e:
        print(f"Error detecting breakouts: {str(e)}")
        return data

def score_breakout_quality(data):
    """
    Score breakout signals from 0-100
    """
    try:
        print("Scoring breakout quality...")
        
        data['Breakout_Score'] = 0
        
        # Only score rows with basic breakouts
        has_breakout = data['Breakout_Basic']
        
        if has_breakout.any():
            # Volume Score (0-25 points)
            volume_ratio = data['Volume'] / data['Volume_MA_20']
            volume_score = np.minimum(volume_ratio * 8, 25)
            data.loc[has_breakout, 'Breakout_Score'] += volume_score[has_breakout]
            
            # Momentum Score (0-25 points)
            rsi_score = np.clip((data['RSI_14'] - 50) * 0.5, 0, 15)  # 0-15 for RSI 50-80
            roc_score = np.clip(data['ROC_10'] * 1.0, 0, 10)  # 0-10 for ROC
            momentum_total = rsi_score + roc_score
            data.loc[has_breakout, 'Breakout_Score'] += momentum_total[has_breakout]
            
            # Trend Score (0-20 points)  
            trend_score = (
                (data['Close'] > data['SMA_10']).astype(int) * 5 +
                (data['SMA_10'] > data['SMA_20']).astype(int) * 5 +
                (data['SMA_20'] > data['SMA_50']).astype(int) * 5 +
                (data['Relative_Strength'] > 1).astype(int) * 5
            )
            data.loc[has_breakout, 'Breakout_Score'] += trend_score[has_breakout]
            
            # Position Score (0-15 points)
            position_score = data['Price_position'] * 0.15
            data.loc[has_breakout, 'Breakout_Score'] += position_score[has_breakout]
            
            # Volatility Context Score (0-15 points) 
            vol_score = np.clip(15 - (data['Volatility_percentile'] * 0.15), 0, 15)
            data.loc[has_breakout, 'Breakout_Score'] += vol_score[has_breakout]
        
        return data
        
    except Exception as e:
        print(f"Error scoring breakouts: {str(e)}")
        return data

def create_visualization(data, ticker):
    """
    Create comprehensive breakout analysis charts
    """
    try:
        print("Creating visualization...")
        
        fig, axes = plt.subplots(4, 1, figsize=(16, 18))
        fig.suptitle(f'{ticker} - Comprehensive Breakout Analysis', fontsize=16, y=0.98)
        
        # 1. Price Chart with Breakouts
        ax1 = axes[0]
        ax1.plot(data.index, data['Close'], label='Close Price', color='black', linewidth=2)
        ax1.plot(data.index, data['BB_upper'], label='BB Upper', color='red', alpha=0.7)
        ax1.plot(data.index, data['BB_middle'], label='BB Middle', color='blue', alpha=0.7, linestyle='--')
        ax1.plot(data.index, data['BB_lower'], label='BB Lower', color='red', alpha=0.7)
        ax1.plot(data.index, data['SMA_20'], label='SMA 20', color='orange', alpha=0.8)
        ax1.plot(data.index, data['SMA_50'], label='SMA 50', color='purple', alpha=0.8)
        
        # Plot breakout signals
        breakout_types = [
            ('Breakout_Premium', 'red', '^', 120, 'Premium'),
            ('Breakout_Quality', 'green', '^', 100, 'Quality'),
            ('Breakout_Consolidation', 'blue', 's', 80, 'Consolidation'),
            ('Breakout_Flag', 'orange', 'd', 80, 'Flag'),
            ('Breakout_Gap', 'purple', '*', 100, 'Gap')
        ]
        
        for col, color, marker, size, label in breakout_types:
            if col in data.columns and data[col].any():
                signals = data[data[col]]
                ax1.scatter(signals.index, signals['Close'], 
                          color=color, marker=marker, s=size, 
                          label=f'{label} ({len(signals)})', zorder=5, alpha=0.8)
        
        ax1.set_ylabel('Price ($)')
        ax1.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.set_title('Price Action & Breakout Signals')
        
        # 2. Volume Analysis
        ax2 = axes[1]
        # Volume bars
        colors = ['red' if vol > 1.5 * ma else 'lightblue' for vol, ma in 
                 zip(data['Volume'], data['Volume_MA_20'])]
        ax2.bar(data.index, data['Volume'], color=colors, alpha=0.6, width=0.8)
        ax2.plot(data.index, data['Volume_MA_20'], color='red', linewidth=2, label='Volume MA 20')
        ax2.plot(data.index, 1.5 * data['Volume_MA_20'], color='orange', 
                linestyle='--', linewidth=1, label='1.5x Volume MA')
        
        ax2.set_ylabel('Volume')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.set_title('Volume Analysis (Red bars = High Volume)')
        
        # 3. Momentum Indicators
        ax3 = axes[2]
        
        # RSI
        ax3.plot(data.index, data['RSI_14'], color='purple', linewidth=2, label='RSI 14')
        ax3.axhline(y=70, color='red', linestyle='--', alpha=0.7, label='Overbought')
        ax3.axhline(y=50, color='gray', linestyle='-', alpha=0.5)
        ax3.axhline(y=30, color='green', linestyle='--', alpha=0.7, label='Oversold')
        ax3.fill_between(data.index, 30, 70, alpha=0.1, color='gray')
        ax3.set_ylabel('RSI')
        ax3.set_ylim(0, 100)
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        
        # MACD on twin axis
        ax3_twin = ax3.twinx()
        ax3_twin.plot(data.index, data['MACD'], color='blue', linewidth=1.5, label='MACD')
        ax3_twin.plot(data.index, data['MACD_signal'], color='red', linewidth=1.5, label='Signal')
        # MACD histogram
        colors_hist = ['green' if x > 0 else 'red' for x in data['MACD_histogram']]
        ax3_twin.bar(data.index, data['MACD_histogram'], alpha=0.3, color=colors_hist, width=0.8)
        ax3_twin.set_ylabel('MACD')
        ax3_twin.legend(loc='upper right')
        ax3.set_title('Momentum: RSI & MACD')
        
        # 4. Breakout Quality Scores
        ax4 = axes[3]
        if 'Breakout_Score' in data.columns:
            scored_days = data[data['Breakout_Score'] > 0]
            if len(scored_days) > 0:
                colors_score = ['darkgreen' if score >= 70 else 'green' if score >= 50 else 'orange' 
                               for score in scored_days['Breakout_Score']]
                ax4.bar(scored_days.index, scored_days['Breakout_Score'], 
                       color=colors_score, alpha=0.8, width=0.8)
                ax4.axhline(y=70, color='red', linestyle='--', linewidth=2, label='Excellent (70+)')
                ax4.axhline(y=50, color='orange', linestyle='--', linewidth=2, label='Good (50+)')
                ax4.set_ylim(0, 100)
        
        ax4.set_ylabel('Breakout Score')
        ax4.set_xlabel('Date')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        ax4.set_title('Breakout Quality Scores')
        
        plt.tight_layout()
        plt.subplots_adjust(top=0.95)
        plt.show()
        
    except Exception as e:
        print(f"Error creating visualization: {str(e)}")

def analyze_performance(data, days_ahead=5):
    """
    Analyze breakout performance
    """
    try:
        print(f"Analyzing breakout performance ({days_ahead} days forward)...")
        
        results = {}
        breakout_types = ['Breakout_Basic', 'Breakout_Quality', 'Breakout_Premium', 
                         'Breakout_Consolidation', 'Breakout_Momentum']
        
        for breakout_type in breakout_types:
            if breakout_type in data.columns and data[breakout_type].any():
                signals = data[data[breakout_type]].copy()
                returns = []
                
                for signal_date in signals.index:
                    try:
                        entry_price = signals.loc[signal_date, 'Close']
                        
                        # Find price after N days
                        future_dates = data.index[data.index > signal_date]
                        if len(future_dates) >= days_ahead:
                            exit_price = data.loc[future_dates[days_ahead-1], 'Close']
                            return_pct = (exit_price - entry_price) / entry_price * 100
                            returns.append(return_pct)
                    except:
                        continue
                
                if returns:
                    results[breakout_type] = {
                        'count': len(signals),
                        'avg_return': np.mean(returns),
                        'median_return': np.median(returns),
                        'win_rate': len([r for r in returns if r > 0]) / len(returns) * 100,
                        'best_return': max(returns),
                        'worst_return': min(returns),
                        'std_dev': np.std(returns)
                    }
        
        return results
        
    except Exception as e:
        print(f"Error analyzing performance: {str(e)}")
        return {}

def print_detailed_summary(data, ticker, performance_results):
    """
    Print comprehensive analysis summary
    """
    print(f"\n{'='*60}")
    print(f"BREAKOUT ANALYSIS SUMMARY FOR {ticker}")
    print(f"{'='*60}")
    
    print(f"Analysis Period: {data.index[0].strftime('%Y-%m-%d')} to {data.index[-1].strftime('%Y-%m-%d')}")
    print(f"Total Trading Days: {len(data)}")
    
    # Breakout counts
    print(f"\n--- BREAKOUT SIGNALS ---")
    breakout_counts = {
        'Basic': data.get('Breakout_Basic', pd.Series()).sum(),
        'Quality': data.get('Breakout_Quality', pd.Series()).sum(),
        'Premium': data.get('Breakout_Premium', pd.Series()).sum(),
        'Consolidation': data.get('Breakout_Consolidation', pd.Series()).sum(),
        'Momentum': data.get('Breakout_Momentum', pd.Series()).sum(),
        'Flag': data.get('Breakout_Flag', pd.Series()).sum(),
        'Gap': data.get('Breakout_Gap', pd.Series()).sum()
    }
    
    for signal_type, count in breakout_counts.items():
        if count > 0:
            print(f"{signal_type:12}: {count:3d} signals")
    
    # High-quality breakouts
    if 'Breakout_Score' in data.columns:
        excellent_breakouts = data[data['Breakout_Score'] >= 70]
        good_breakouts = data[data['Breakout_Score'] >= 50]
        
        print(f"\n--- QUALITY BREAKDOWN ---")
        print(f"Excellent (70+ score): {len(excellent_breakouts)} signals")
        print(f"Good (50+ score):      {len(good_breakouts)} signals")
        
        if len(excellent_breakouts) > 0:
            print(f"\n--- TOP BREAKOUTS ---")
            top_breakouts = excellent_breakouts.nlargest(5, 'Breakout_Score')
            for date, row in top_breakouts.iterrows():
                print(f"{date.strftime('%Y-%m-%d')}: Score {row['Breakout_Score']:.1f}, "
                      f"Price ${row['Close']:.2f}, Volume {row['Volume']:,.0f}")
    
    # Performance analysis
    if performance_results:
        print(f"\n--- PERFORMANCE ANALYSIS (5-day forward returns) ---")
        print(f"{'Type':<15} {'Count':<6} {'Avg%':<8} {'Med%':<8} {'Win%':<6} {'Best%':<8} {'Worst%':<8}")
        print("-" * 70)
        
        for breakout_type, stats in performance_results.items():
            type_name = breakout_type.replace('Breakout_', '')
            print(f"{type_name:<15} {stats['count']:<6} {stats['avg_return']:<8.1f} "
                  f"{stats['median_return']:<8.1f} {stats['win_rate']:<6.1f} "
                  f"{stats['best_return']:<8.1f} {stats['worst_return']:<8.1f}")

def main():
    """
    Main analysis function
    """
    # Configuration
    TICKER = 'NVDA'
    START_DATE = '2024-01-01'
    END_DATE = '2025-09-07'
    
    print("🚀 ENHANCED STOCK BREAKOUT ANALYZER 🚀")
    print(f"Target: {TICKER}")
    print(f"Period: {START_DATE} to {END_DATE}")
    
    # Execute analysis pipeline
    data = fetch_stock_data(TICKER, START_DATE, END_DATE)
    if data is None:
        print("❌ Failed to fetch data. Exiting.")
        return None
    
    data = calculate_technical_indicators(data)
    if data is None:
        print("❌ Failed to calculate indicators. Exiting.")
        return None
    
    data = detect_breakout_patterns(data)
    data = score_breakout_quality(data)
    
    # Analyze performance
    performance_results = analyze_performance(data, days_ahead=5)
    
    # Print comprehensive summary
    print_detailed_summary(data, TICKER, performance_results)
    
    # Create visualization
    create_visualization(data, TICKER)
    
    print(f"\n✅ Analysis complete! Found breakout opportunities in {TICKER}")
    print("💡 Focus on 'Premium' and 'Quality' breakouts with scores 70+ for best results")
    
    return data

# Execute the analysis
if __name__ == "__main__":
    result_data = main()