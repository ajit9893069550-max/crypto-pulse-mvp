# parser.py
import re
# Assuming config.py is in the same directory
from config import SUPPORTED_ASSETS, SUPPORTED_TIMEFRAMES

def parse_alert_request(text):
    """
    Parses a user's natural language request into a machine-readable dictionary.
    
    Args:
        text (str): The raw text from the user 
        
    Returns:
        dict: A dictionary of parsed parameters or an error dict if parsing fails.
    """
    
    # Convert input to uppercase for case-insensitive matching
    text = text.upper()
    alert_params = {}
    
    # --- 1. ASSET EXTRACTION ---
    asset_match = re.search(r'\b(BTC|ETH|SOL|BNB|ADA)\b', text)
    if asset_match:
        asset_ticker = asset_match.group(1)
        alert_params['asset'] = SUPPORTED_ASSETS.get(asset_ticker)
    else:
        return {'error': 'Could not identify a supported asset (BTC, ETH, SOL, BNB, ADA).'}

    # --- 2. TIMEFRAME EXTRACTION (Guaranteed Fix) ---
    # Start with the default to ensure a value is always present, preventing the 'None' error.
    alert_params['timeframe'] = '4h'

    # Looks for patterns like '4H', '1D', 'DAILY', 'HOURLY', etc.
    # The regex allows any number followed by H, D, W, M, or S, or the full words.
    tf_match = re.search(r'(\d+[HDWMS]|DAILY|HOURLY)', text)
    
    if tf_match:
        # Normalize the key (e.g., '1H' or 'DAILY')
        tf_key = tf_match.group(1).lower().replace('h', 'H').replace('d', 'D')
        
        # Check if the normalized key is valid in SUPPORTED_TIMEFRAMES
        if SUPPORTED_TIMEFRAMES.get(tf_key):
             alert_params['timeframe'] = SUPPORTED_TIMEFRAMES.get(tf_key)
        # If the key is found but not in our SUPPORTED_TIMEFRAMES (e.g., '5W'), 
        # it correctly keeps the default '4h'.

    # --- 3. MA CROSSOVER LOGIC ---
    ma_match = re.findall(r'(\d+)\s*(?:M\.A|E\.M\.A|S\.M\.A|MA|EMA|SMA)', text)
    if len(ma_match) == 2 and 'CROSS' in text:
        alert_params['type'] = 'MA_CROSS'
        alert_params['fast_ma'] = int(ma_match[0])
        alert_params['slow_ma'] = int(ma_match[1])
        alert_params['condition'] = 'ABOVE' if 'ABOVE' in text or 'OVER' in text else 'BELOW'
        return alert_params
    
    # --- 4. SIMPLE PRICE LEVEL LOGIC (CORRECTED REGEX) ---
    # Flexible Regex: captures number, allows optional space/punctuation, and then optional K/$/DOLLAR.
    price_match = re.search(r'(\d+\.?\d*)\s*[,.\s]*(?:K|\$|DOLLAR)?', text)
    
    if price_match and ('HIT' in text or 'ABOVE' in text or 'BELOW' in text or 'DROPS' in text):
        alert_params['type'] = 'PRICE_LEVEL'
        
        price_target = float(price_match.group(1))
        
        # Handle 'K' (thousands) suffix
        if re.search(r'\d+\s*K', text):
            price_target *= 1000
            
        alert_params['target_price'] = price_target
        
        # Determine the condition
        if 'ABOVE' in text or 'OVER' in text:
            alert_params['condition'] = 'ABOVE'
        elif 'BELOW' in text or 'DROPS' in text:
            alert_params['condition'] = 'BELOW'
        else:
            alert_params['condition'] = 'HIT'
            
        return alert_params
    
    # If no supported alert type is found
    return {'error': 'Alert type (MA Cross or Price) not recognized.'}


if __name__ == '__main__':
    # --- TESTING THE PARSER ---
    test_phrases = [
        # Test 1: Successful MA Cross
        "Alert me when BTC 50 MA crosses 200 MA on the 4h chart", 
        # Test 2: Successful Price Level (using the previously failing format)
        "If ETH drops below 500, alert me please on the 1h chart", 
        # Test 3: Price Level with default timeframe
        "If BNB hits 300, alert me"
    ]
    
    for phrase in test_phrases:
        print(f"\nUser: {phrase}")
        result = parse_alert_request(phrase)
        print(f"Parsed: {result}")