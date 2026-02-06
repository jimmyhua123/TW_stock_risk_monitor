"""
Debug script to test P/C Ratio history fetching
"""
import requests

TAIFEX_BASE_URL = "https://www.taifex.com.tw"

def test_pc_ratio():
    date_str = "20260130"
    num_days = 5
    
    url = f"{TAIFEX_BASE_URL}/cht/3/pcRatioDown"
    formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
    params = {'queryDate': formatted_date}
    
    print(f"[DEBUG] Requesting: {url}")
    print(f"[DEBUG] Params: {params}")
    
    response = requests.post(url, data=params, timeout=10)
    
    print(f"[DEBUG] Status: {response.status_code}")
    print(f"[DEBUG] Raw text (first 500 chars):\n{response.text[:500]}")
    print()
    
    # Parse manually
    lines = response.text.strip().split('\n')
    print(f"[DEBUG] Total lines: {len(lines)}")
    print(f"[DEBUG] Header: {lines[0]}")
    print()
    
    pc_ratios = []
    target_date_int = int(date_str)
    
    for i, line in enumerate(lines[1:], start=1):
        parts = line.strip().split(',')
        print(f"[DEBUG] Line {i}: {parts}")
        
        if len(parts) >= 7:
            row_date = parts[0].replace('/', '')
            pc_value = parts[6]  # Last column
            print(f"  -> Date: {row_date}, P/C Ratio: {pc_value}")
            
            try:
                if int(row_date) <= target_date_int:
                    pc_ratios.append(float(pc_value))
                    if len(pc_ratios) >= num_days:
                        break
            except Exception as e:
                print(f"  -> ERROR: {e}")
        
        if i >= 10:  # Only show first 10 lines for debugging
            break
    
    print()
    print(f"[RESULT] Collected P/C Ratios: {pc_ratios}")
    if pc_ratios:
        avg = sum(pc_ratios) / len(pc_ratios)
        print(f"[RESULT] 5-Day Average: {avg:.2f}%")

if __name__ == "__main__":
    test_pc_ratio()
