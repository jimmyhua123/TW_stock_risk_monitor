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
from datetime import datetime

class NpEncoder(json.JSONEncoder):
    """處理 NumPy 數據類型的 JSON Encoder"""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.strftime('%Y-%m-%d')
        return super(NpEncoder, self).default(obj)

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
        # 讀取所有工作表
        # header=2 因為通常前兩行是標題大字和說明，第三行才是欄位名稱
        # 根據 main.py 的輸出格式:
        # 總覽: A1是大標題, A3是欄位 -> header=2 (0-indexed)
        # 詳細數據: A1是大標題, A3是小標題 -> 結構比較特殊，可能需要個別處理
        # 個股籌碼: A1是大標題, A3是欄位 -> header=2
        
        xls = pd.ExcelFile(input_path)
        data = {}
        
        for sheet_name in xls.sheet_names:
            print(f"  處理工作表: {sheet_name}")
            
            # 預設讀取方式 (假設標題在第3行，即 index 2)
            header_idx = 2
            
            # 特殊處理 "詳細數據" 工作表，它的結構比較像 Key-Value 列表，不僅僅是表格
            if sheet_name == "詳細數據":
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                # 將其轉為單純的 list of lists，交由 AI 自行理解結構
                sheet_data = df.where(pd.notnull(df), None).values.tolist()
            else:
                # 對於 "總覽" 和 "個股籌碼"，嘗試以 dataframe 讀取
                df = pd.read_excel(xls, sheet_name=sheet_name, header=header_idx)
                
                # 移除完全空白的行與列
                df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
                
                # 將 NaN 替換為 None (對應 JSON null)
                df = df.where(pd.notnull(df), None)
                
                sheet_data = df.to_dict(orient='records')
            
            data[sheet_name] = sheet_data

        # 生成輸出路徑
        if not output_path:
            # 預設輸出到 json/ 資料夾
            output_dir = 'json'
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}.json")
        else:
            # 如果使用者指定了路徑，確保該路徑的資料夾存在
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

        # 寫入 JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=NpEncoder, ensure_ascii=False, indent=indent)
            
        print(f"[SUCCESS] 轉換完成！已儲存至: {output_path}")
        
        # 轉換為 TXT
        convert_json_to_txt(output_path)
        
    except Exception as e:
        print(f"[ERROR] 轉換失敗: {e}")
        import traceback
        traceback.print_exc()

def convert_json_to_txt(json_path: str, output_path: str = None):
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
            output_dir = 'txt'
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            base_name = os.path.splitext(os.path.basename(json_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}.txt")
        else:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

        with open(output_path, 'w', encoding='utf-8') as f:
            if isinstance(data, dict):
                for sheet_name, sheet_data in data.items():
                    f.write(f"=== {sheet_name} ===\n")
                    if isinstance(sheet_data, list):
                        for row in sheet_data:
                            if isinstance(row, dict):
                                row_str = ", ".join([f"{k}: {v}" for k, v in row.items() if v is not None])
                                f.write(f"- {row_str}\n")
                            elif isinstance(row, list):
                                row_str = ", ".join([str(x) for x in row if x is not None])
                                f.write(f"- {row_str}\n")
                            else:
                                f.write(f"- {row}\n")
                    else:
                        f.write(f"{sheet_data}\n")
                    f.write("\n")
            else:
                f.write(json.dumps(data, ensure_ascii=False, indent=2))
                
        print(f"[SUCCESS] TXT 轉換完成！已儲存至: {output_path}")
        
    except Exception as e:
        print(f"[ERROR] TXT 轉換失敗: {e}")

def batch_convert(input_dir: str = 'monitor_xlsx', output_dir: str = 'json', force: bool = False):
    """
    批量轉換資料夾內所有 Excel 檔案
    
    Args:
        input_dir: 輸入資料夾路徑
        output_dir: 輸出資料夾路徑
        force: 是否強制重新轉換已存在的檔案
    """
    if not os.path.exists(input_dir):
        print(f"[ERROR] 輸入資料夾不存在: {input_dir}")
        return
    
    # 確保輸出資料夾存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 取得所有 xlsx 檔案
    xlsx_files = [f for f in os.listdir(input_dir) if f.endswith('.xlsx')]
    
    if not xlsx_files:
        print(f"[INFO] 資料夾 {input_dir} 中沒有 xlsx 檔案")
        return
    
    print(f"[INFO] 找到 {len(xlsx_files)} 個 Excel 檔案")
    
    converted_count = 0
    skipped_count = 0
    
    for xlsx_file in sorted(xlsx_files):
        input_path = os.path.join(input_dir, xlsx_file)
        base_name = os.path.splitext(xlsx_file)[0]
        output_path = os.path.join(output_dir, f"{base_name}.json")
        
        # 檢查是否已轉換
        if os.path.exists(output_path) and not force:
            # 比較修改時間，如果 Excel 較新才需要重新轉換
            xlsx_mtime = os.path.getmtime(input_path)
            json_mtime = os.path.getmtime(output_path)
            
            if xlsx_mtime <= json_mtime:
                # 檢查對應的 TXT 是否存在且最新
                txt_path = os.path.join('txt', f"{base_name}.txt")
                if os.path.exists(txt_path):
                    txt_mtime = os.path.getmtime(txt_path)
                    if json_mtime <= txt_mtime:
                        print(f"[SKIP] {xlsx_file} (JSON 與 TXT 皆已存在且為最新)")
                        skipped_count += 1
                        continue
                
                # 如 JSON 存在但 TXT 遺失或較舊，進行補轉
                print(f"[INFO] {xlsx_file} (補轉 TXT...)")
                convert_json_to_txt(output_path)
                converted_count += 1
                continue
        
        convert_excel_to_json(input_path, output_path)
        converted_count += 1
    
    print()
    print(f"[SUMMARY] 轉換完成: {converted_count} 個, 跳過: {skipped_count} 個")


def main():
    parser = argparse.ArgumentParser(
        description='Excel to JSON Converter for Stock Risk Monitor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 批量轉換 monitor_xlsx 資料夾內所有檔案
  python excel_to_json.py
  
  # 強制重新轉換所有檔案
  python excel_to_json.py --force
  
  # 轉換單一檔案
  python excel_to_json.py monitor_xlsx/20260205.xlsx
  
  # 將 json 轉為 txt
  python excel_to_json.py --json2txt json/20260205.json
        """
    )
    parser.add_argument('input', nargs='?', help='輸入的 Excel 檔案路徑 (.xlsx)，不指定則批量轉換')
    parser.add_argument('--output', '-o', help='輸出的 JSON 檔案路徑 (選填)')
    parser.add_argument('--indent', type=int, default=2, help='JSON 縮排 (預設: 2)')
    parser.add_argument('--force', '-f', action='store_true', help='強制重新轉換所有檔案')
    parser.add_argument('--json2txt', help='將指定的 JSON 檔案轉為 TXT')
    
    args = parser.parse_args()
    
    if args.json2txt:
        convert_json_to_txt(args.json2txt)
    elif args.input:
        # 單一檔案模式
        convert_excel_to_json(args.input, args.output, args.indent)
    else:
        # 批量轉換模式
        batch_convert(force=args.force)


if __name__ == '__main__':
    main()

