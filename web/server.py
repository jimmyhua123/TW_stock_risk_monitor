#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Dashboard 本地伺服器
提供 API 列出 / 讀取 outputs 資料夾中的報告檔案，
並 Serve web/ 目錄的靜態檔案。

啟動方式: python web/server.py
瀏覽器開啟: http://localhost:8080
"""

import os
import sys
import json
import re
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 專案根目錄 (server.py 在 web/ 底下，所以往上一層)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEB_DIR = os.path.join(PROJECT_ROOT, 'web')

# 四個資料來源目錄的對照
DIR_MAP = {
    'json':        os.path.join(PROJECT_ROOT, 'outputs', 'json'),
    'global_json': os.path.join(PROJECT_ROOT, 'outputs', 'global_json'),
    'reports':     os.path.join(PROJECT_ROOT, 'outputs', 'reports'),
    'qd':          os.path.join(PROJECT_ROOT, 'QD_twstock', 'result'),
}

class DashboardHandler(SimpleHTTPRequestHandler):
    """自訂 HTTP Handler，處理 API 和靜態檔案"""

    def __init__(self, *args, **kwargs):
        # 設定靜態檔案根目錄為 web/
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/list':
            self.handle_list(parse_qs(parsed.query))
        elif path == '/api/file':
            self.handle_file(parse_qs(parsed.query))
        else:
            # 靜態檔案 (index.html, app.js, style.css ...)
            super().do_GET()

    def handle_list(self, params):
        """列出指定目錄的檔案清單，按檔名倒序排列"""
        dir_key = params.get('dir', [''])[0]
        if dir_key not in DIR_MAP:
            self.send_json({'error': f'Unknown dir: {dir_key}'}, 400)
            return

        target_dir = DIR_MAP[dir_key]
        if not os.path.isdir(target_dir):
            self.send_json({'files': []})
            return

        files = []
        for f in os.listdir(target_dir):
            full_path = os.path.join(target_dir, f)
            if os.path.isfile(full_path):
                files.append({
                    'name': f,
                    'size': os.path.getsize(full_path),
                    'mtime': os.path.getmtime(full_path)
                })

        # 按檔名倒序排列 (最新的日期在前面)
        files.sort(key=lambda x: x['name'], reverse=True)
        self.send_json({'dir': dir_key, 'files': files})

    def handle_file(self, params):
        """回傳指定檔案的內容"""
        dir_key = params.get('dir', [''])[0]
        filename = params.get('name', [''])[0]

        if dir_key not in DIR_MAP or not filename:
            self.send_json({'error': 'Missing dir or name parameter'}, 400)
            return

        # 安全性檢查：防止路徑穿越
        target_dir = DIR_MAP[dir_key]
        filepath = os.path.normpath(os.path.join(target_dir, filename))
        if not filepath.startswith(target_dir):
            self.send_json({'error': 'Access denied'}, 403)
            return

        if not os.path.isfile(filepath):
            self.send_json({'error': f'File not found: {filename}'}, 404)
            return

        # 判定 Content-Type
        mime, _ = mimetypes.guess_type(filepath)
        if mime is None:
            mime = 'application/octet-stream'

        try:
            if mime.startswith('text/') or mime == 'application/json':
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 清理 Python 輸出的非標準 JSON 值 (NaN, Infinity, -Infinity)
                if mime == 'application/json':
                    content = re.sub(r'\bNaN\b', 'null', content)
                    content = re.sub(r'\b-Infinity\b', 'null', content)
                    content = re.sub(r'\bInfinity\b', 'null', content)
                self.send_response(200)
                self.send_header('Content-Type', f'{mime}; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            else:
                with open(filepath, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)

    def send_json(self, data, status=200):
        """回傳 JSON 回應"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def log_message(self, format, *args):
        """自訂 log 格式"""
        sys.stderr.write(f"[Dashboard] {args[0]}\n")


def main():
    port = 8080
    server = HTTPServer(('0.0.0.0', port), DashboardHandler)
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Dashboard Server 啟動成功                  ║")
    print(f"║  瀏覽器開啟: http://localhost:{port}           ║")
    print(f"║  按 Ctrl+C 關閉                             ║")
    print(f"╚══════════════════════════════════════════════╝")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 伺服器已關閉")
        server.server_close()


if __name__ == '__main__':
    main()
