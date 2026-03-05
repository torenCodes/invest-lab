import yfinance as yf
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

def fetch_and_analyze_stock(ticker='AMD', start_date='2024-01-01', end_date='2025-09-07'):
    """
    Fetch stock data and analyze for breakout patterns
    """
    try:
        # Ensure ticker is string
        if isinstance(ticker, list):
            ticker = ticker[0]
        
        print(f"Fetching data for {ticker}...")
        
        # Fetch data with error handling
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        # Handle empty data
        if data.empty:
            print(f"No data found for {ticker}. Check ticker symbol and date range.")
            return None
            
        # Flatten multi-level columns if present
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        
        # Ensure we have the required columns
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            print(f"Missing required columns: {missing_columns}")
            return None
        
        # Remove any rows with NaN values in critical columns
        data = data.dropna(subset=['Close', 'Volume'])
        
        print(f"Successfully downloaded {len(data)} rows of data")
        print(f"Date range: {data.index[0]} to {data.index[-1]}")
        
        # Ensure we have enough data for analysis
        min_data_points = 25
        if len(data) < min_data_points:
            print(f"Not enough data points. Need at least {min_data_points}, got {len(data)}")
            return None
            
        return data
        
    except Exception as e:
        print(f"Error fetching data: {str(e)}")
        return None

def calculate_indicators(data):
    """
    Calculate technical indicators with error handling
    """
    try:
        # Calculate RSI
        data['RSI'] = ta.rsi(data['Close'], length=14)
        
        # Calculate Bollinger Bands with error handling
        bb_length = min(20, len(data) - 1)
        bb = ta.bbands(data['Close'], length=bb_length, std=2)
        
        if bb is not None and not bb.empty:
            # Get the actual column names (they might vary)
            bb_columns = bb.columns.tolist()
            
            # Find columns containing the band indicators
            lower_col = [col for col in bb_columns if 'BBL' in col][0] if any('BBL' in col for col in bb_columns) else None
            middle_col = [col for col in bb_columns if 'BBM' in col][0] if any('BBM' in col for col in bb_columns) else None
            upper_col = [col for col in bb_columns if 'BBU' in col][0] if any('BBU' in col for col in bb_columns) else None
            
            if all([lower_col, middle_col, upper_col]):
                data['BB_lower'] = bb[lower_col]
                data['BB_middle'] = bb[middle_col]
                data['BB_upper'] = bb[upper_col]
                print("Bollinger Bands calculated successfully")
            else:
                print("Could not identify Bollinger Band columns, using fallback")
                data['BB_lower'] = data['Close'] * 0.95
                data['BB_middle'] = data['Close']
                data['BB_upper'] = data['Close'] * 1.05
        else:
            print("Bollinger Bands calculation failed, using fallback")
            data['BB_lower'] = data['Close'] * 0.95
            data['BB_middle'] = data['Close']
            data['BB_upper'] = data['Close'] * 1.05
        
        # Calculate Volume Moving Average
        data['Volume_MA'] = data['Volume'].rolling(window=20, min_periods=1).mean()
        
        # Remove any NaN values that might have been introduced
        data = data.dropna()
        
        print(f"Indicators calculated. Final dataset has {len(data)} rows")
        return data
        
    except Exception as e:
        print(f"Error calculating indicators: {str(e)}")
        return None

def detect_breakouts(data):
    """
    Detect potential breakout signals
    """
    try:
        # Ensure we have all required columns
        required_cols = ['Close', 'BB_upper', 'Volume', 'Volume_MA', 'RSI']
        if not all(col in data.columns for col in required_cols):
            missing = [col for col in required_cols if col not in data.columns]
            print(f"Missing columns for breakout detection: {missing}")
            return data
        
        # Create breakout signal
        conditions = [
            data['Close'] > data['BB_upper'],
            data['Volume'] > 1.5 * data['Volume_MA'],
            data['RSI'] > 55
        ]
        
        # Use numpy to combine conditions
        data['Breakout_Signal'] = np.all(conditions, axis=0)
        
        return data
        
    except Exception as e:
        print(f"Error detecting breakouts: {str(e)}")
        return data

def plot_analysis(data, ticker):
    """
    Create visualization of the analysis
    """
    try:
        plt.figure(figsize=(15, 10))
        
        # Main price and Bollinger Bands plot
        plt.subplot(2, 1, 1)
        plt.plot(data.index, data['Close'], label='Close Price', linewidth=1.5)
        plt.plot(data.index, data['BB_upper'], label='Upper Bollinger', alpha=0.7, color='red')
        plt.plot(data.index, data['BB_middle'], label='Middle Bollinger', alpha=0.7, color='blue', linestyle='--')
        plt.plot(data.index, data['BB_lower'], label='Lower Bollinger', alpha=0.7, color='red')
        
        # Mark breakout signals
        breakout_dates = data.index[data['Breakout_Signal']]
        breakout_prices = data['Close'][data['Breakout_Signal']]
        
        if len(breakout_dates) > 0:
            plt.scatter(breakout_dates, breakout_prices, 
                       marker='^', color='green', s=100, 
                       label=f'Breakout Signals ({len(breakout_dates)})', zorder=5)
        
        plt.title(f'{ticker} - Price and Bollinger Bands with Breakout Signals')
        plt.ylabel('Price ($)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Volume subplot
        plt.subplot(2, 1, 2)
        plt.plot(data.index, data['Volume'], alpha=0.6, color='gray', label='Volume')
        plt.plot(data.index, data['Volume_MA'], color='orange', label='Volume MA (20)')
        plt.plot(data.index, 1.5 * data['Volume_MA'], color='red', linestyle='--', alpha=0.7, label='1.5x Volume MA')
        
        # Highlight breakout volume
        if len(breakout_dates) > 0:
            breakout_volumes = data['Volume'][data['Breakout_Signal']]
            plt.scatter(breakout_dates, breakout_volumes, 
                       marker='^', color='green', s=100, zorder=5)
        
        plt.title('Volume Analysis')
        plt.xlabel('Date')
        plt.ylabel('Volume')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
        
    except Exception as e:
        print(f"Error creating plot: {str(e)}")

def main():
    """
    Main execution function
    """
    # Configuration
    ticker = 'AMD'
    start_date = '2024-01-01'
    end_date = '2025-09-07'
    
    print("=== Stock Breakout Analysis ===")
    print(f"Analyzing {ticker} from {start_date} to {end_date}")
    print("-" * 40)
    
    # Fetch data
    data = fetch_and_analyze_stock(ticker, start_date, end_date)
    if data is None:
        return
    
    # Calculate indicators
    data = calculate_indicators(data)
    if data is None:
        return
    
    # Detect breakouts
    data = detect_breakouts(data)
    
    # Print summary statistics
    print("\n=== Analysis Summary ===")
    print(f"Total trading days analyzed: {len(data)}")
    
    if 'Breakout_Signal' in data.columns:
        total_signals = data['Breakout_Signal'].sum()
        print(f"Potential breakout signals detected: {total_signals}")
        
        if total_signals > 0:
            # Show dates of breakouts
            breakout_dates = data.index[data['Breakout_Signal']].tolist()
            print(f"Breakout dates: {[d.strftime('%Y-%m-%d') for d in breakout_dates[:5]]}")
            if len(breakout_dates) > 5:
                print(f"... and {len(breakout_dates) - 5} more")
            
            # Calculate some basic statistics
            avg_rsi_on_breakout = data[data['Breakout_Signal']]['RSI'].mean()
            avg_volume_ratio = (data[data['Breakout_Signal']]['Volume'] / 
                              data[data['Breakout_Signal']]['Volume_MA']).mean()
            
            print(f"Average RSI during breakouts: {avg_rsi_on_breakout:.1f}")
            print(f"Average volume ratio during breakouts: {avg_volume_ratio:.1f}x")
    
    # Create visualization
    plot_analysis(data, ticker)
    
    # Return data for further analysis
    return data

# Run the analysis
if __name__ == "__main__":
    result_data = main()