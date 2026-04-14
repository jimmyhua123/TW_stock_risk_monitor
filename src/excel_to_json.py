#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel 轉 JSON 工具
將風險監控報告 (.xlsx) 轉換為 AI 易讀的 JSON 格式
"""

import pandas as pd
import json
import argparse
import os
import numpy as np
import math
from datetime import datetime

class NpEncoder(json.JSONEncoder):
    """處理 NumPy 數據類型的 JSON Encoder"""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, float):
            if obj != obj or obj == float('inf') or obj == float('-inf'):  # NaN check
                return None
        return super(NpEncoder, self).default(obj)

def sanitize_for_json(obj):
    """遞迴清理資料結構中的 NaN / Infinity，替換為 None (JSON null)"""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj

def convert_excel_to_json(input_path: str, output_path: str = None, indent: int = 2):
    """
    將 Excel 檔案轉換為 formatted JSON
    
    Args:
        input_path: Excel 檔案路徑
        output_path: JSON 輸出路徑 (預設為同檔名 .json)
        indent: JSON 縮排空格數
    """
    
    if not os.path.exists(input_path):
        print(f"[ERROR] 找不到檔案: {input_path}")
        return

    print(f"[INFO] 正在讀取 Excel: {input_path}")
    
    try:
        xls = pd.ExcelFile(input_path)
        data = {}
        
        # 判定是否為全球市場報表 (看工作表名稱)
        is_global = "Global Markets" in xls.sheet_names or "Macro Data" in xls.sheet_names
        
        for sheet_name in xls.sheet_names:
            print(f"  處理工作表: {sheet_name}")
            
            # 預設讀取方式
            # 台灣風險報表: 標題在第 3 行 (header=2)
            # 全球市場報表: 標題在第 1 行 (header=0)
            header_idx = 0 if is_global else 2
            
            if sheet_name == "詳細數據":
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                sheet_data = df.where(pd.notnull(df), None).values.tolist()
            else:
                df = pd.read_excel(xls, sheet_name=sheet_name, header=header_idx)
                df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
                df = df.where(pd.notnull(df), None)
                sheet_data = df.to_dict(orient='records')
            
            data[sheet_name] = sheet_data

        # 生成輸出路徑
        if not output_path:
            # 依據類型決定目錄
            sub_dir = 'global_json' if is_global else 'json'
            output_dir = os.path.join('outputs', sub_dir)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}.json")
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

        # 清理 NaN / Infinity 為 null
        data = sanitize_for_json(data)

        # 寫入 JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=NpEncoder, ensure_ascii=False, indent=indent)
            
        print(f"[SUCCESS] 轉換完成！已儲存至: {output_path}")
        
        # 轉換為 TXT
        # 傳遞 is_global 讓 TXT 知道如何處理輸出目錄
        convert_json_to_txt(output_path, is_global=is_global)
        
    except Exception as e:
        print(f"[ERROR] 轉換失敗: {e}")
        import traceback
        traceback.print_exc()

def convert_json_to_txt(json_path: str, output_path: str = None, is_global: bool = False):
    """
    將 JSON 檔案轉換為純文字 TXT 格式
    """
    if not os.path.exists(json_path):
        print(f"[ERROR] 找不到 JSON 檔案: {json_path}")
        return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if not output_path:
            # 依據類型決定目錄
            sub_dir = 'global_txt' if is_global or 'market_data' in data else 'txt'
            output_dir = os.path.join('outputs', sub_dir)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            base_name = os.path.splitext(os.path.basename(json_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}.txt")
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

        with open(output_path, 'w', encoding='utf-8') as f:
            def write_recursive(obj, level=0):
                indent = "  " * level
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, (dict, list)):
                            f.write(f"{indent}=== {k} ===\n")
                            write_recursive(v, level + 1)
                        else:
                            f.write(f"{indent}- {k}: {v}\n")
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            # 將 dict 的內容壓縮成一行
                            row_str = ", ".join([f"{k}: {v}" for k, v in item.items() if v is not None])
                            f.write(f"{indent}- {row_str}\n")
                        elif isinstance(item, list):
                            row_str = ", ".join([str(x) for x in item if x is not None])
                            f.write(f"{indent}- {row_str}\n")
                        else:
                            f.write(f"{indent}- {item}\n")
                else:
                    f.write(f"{indent}{obj}\n")

            # 如果 JSON 頂層有資料，開始遞迴寫入
            if isinstance(data, dict):
                write_recursive(data)
            else:
                f.write(json.dumps(data, ensure_ascii=False, indent=2))
                
        print(f"[SUCCESS] TXT 轉換完成！已儲存至: {output_path}")
        
    except Exception as e:
        print(f"[ERROR] TXT 轉換失敗: {e}")


def batch_convert(input_dir: str = os.path.join('outputs', 'monitor_xlsx'), output_dir: str = os.path.join('outputs', 'json'), force: bool = False, is_global: bool = False):
    """
    批量轉換資料夾內所有 Excel 檔案
    """
    if not os.path.exists(input_dir):
        print(f"[ERROR] 輸入資料夾不存在: {input_dir}")
        return
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    xlsx_files = [f for f in os.listdir(input_dir) if f.endswith('.xlsx')]
    
    if not xlsx_files:
        print(f"[INFO] 資料夾 {input_dir} 中沒有 xlsx 檔案")
        return
    
    print(f"[INFO] 找到 {len(xlsx_files)} 個 Excel 檔案")
    
    converted_count = 0
    skipped_count = 0
    
    txt_sub_dir = 'global_txt' if is_global else 'txt'
    
    for xlsx_file in sorted(xlsx_files):
        input_path = os.path.join(input_dir, xlsx_file)
        base_name = os.path.splitext(xlsx_file)[0]
        output_path = os.path.join(output_dir, f"{base_name}.json")
        
        if os.path.exists(output_path) and not force:
            xlsx_mtime = os.path.getmtime(input_path)
            json_mtime = os.path.getmtime(output_path)
            
            if xlsx_mtime <= json_mtime:
                txt_path = os.path.join('outputs', txt_sub_dir, f"{base_name}.txt")
                if os.path.exists(txt_path):
                    txt_mtime = os.path.getmtime(txt_path)
                    if json_mtime <= txt_mtime:
                        print(f"[SKIP] {xlsx_file}")
                        skipped_count += 1
                        continue
                
                print(f"[INFO] {xlsx_file} (補轉 TXT...)")
                convert_json_to_txt(output_path, is_global=is_global)
                converted_count += 1
                continue
        
        convert_excel_to_json(input_path, output_path)
        converted_count += 1
    
    print()
    print(f"[SUMMARY] 轉換完成: {converted_count} 個, 跳過: {skipped_count} 個")

def main():
    parser = argparse.ArgumentParser(
        description='Excel to JSON/TXT Converter for Stock Risk Monitor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 批量轉換 monitor_xlsx 資料夾內所有檔案 (台灣)
  python excel_to_json.py
  
  # 批量轉換 global_xlsx 資料夾內所有檔案 (全球)
  python excel_to_json.py --global
  
  # 強制重新轉換所有檔案
  python excel_to_json.py --force
  
  # 轉換單一檔案
  python src/excel_to_json.py outputs/monitor_xlsx/20260205.xlsx
        """
    )
    parser.add_argument('input', nargs='?', help='輸入的 Excel 檔案路徑 (.xlsx)，不指定則批量轉換')
    parser.add_argument('--output', '-o', help='輸出的 JSON 檔案路徑 (選填)')
    parser.add_argument('--indent', type=int, default=2, help='JSON 縮排 (預設: 2)')
    parser.add_argument('--force', '-f', action='store_true', help='強制重新轉換所有檔案')
    parser.add_argument('--global_market', '--global', action='store_true', help='批量轉換全球市場報表 (global_xlsx)')
    parser.add_argument('--json2txt', help='將指定的 JSON 檔案轉為 TXT')
    
    args = parser.parse_args()
    
    if args.json2txt:
        convert_json_to_txt(args.json2txt, is_global=args.global_market)
    elif args.input:
        convert_excel_to_json(args.input, args.output, args.indent)
    elif args.global_market:
        # 僅執行全球市場批量轉換
        batch_convert(
            input_dir=os.path.join('outputs', 'global_xlsx'),
            output_dir=os.path.join('outputs', 'global_json'),
            force=args.force,
            is_global=True
        )
    else:
        # 預設執行全部批量轉換 (台灣 + 全球)
        print("=== 開始批量轉換: 台灣風險報表 ===")
        batch_convert(force=args.force)
        
        print("\n=== 開始批量轉換: 全球市場報表 ===")
        batch_convert(
            input_dir=os.path.join('outputs', 'global_xlsx'),
            output_dir=os.path.join('outputs', 'global_json'),
            force=args.force,
            is_global=True
        )


if __name__ == '__main__':
    main()

