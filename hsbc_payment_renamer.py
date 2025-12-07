#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HSBC Payment Advice PDF 重新命名工具
用於自動提取 HSBC Payment Advice PDF 中的資訊並重新命名檔案

命名格式: YY_PX_BENE_CODE_OUTLETNUM.pdf
"""

import fitz  # PyMuPDF
import os
import re
from pathlib import Path
import argparse
from datetime import datetime


class HSBCPaymentAdviceRenamer:
    """HSBC Payment Advice PDF 重新命名工具"""
    
    def __init__(self):
        """初始化重新命名工具"""
        self.supported_extensions = ['.pdf']
        
    def extract_pdf_info(self, pdf_path):
        """
        從 HSBC Payment Advice PDF 中提取資訊
        
        Args:
            pdf_path (str): PDF 檔案路徑
            
        Returns:
            dict: 提取的資訊字典，包含 year, outlet_num, bene_abbr, outlet_code
        """
        try:
            # 開啟 PDF 文件
            doc = fitz.open(pdf_path)
            page = doc[0]  # 只需要第一頁
            text = page.get_text("text")
            doc.close()
        except Exception as e:
            print(f"  [錯誤] 無法開啟或讀取 PDF '{os.path.basename(pdf_path)}'。原因: {e}")
            return None

        extracted_info = {}

        # --- 1. 提取年份 (YY) ---
        # 尋找 "Advice sending date" 行並提取年份
        # 格式: "20 Jun 2025" 或 "Advice sending date 通知書發出日期:\n20 Jun 2025"
        date_match = re.search(r"Advice sending date.*?(\d{1,2}\s+\w{3}\s+(\d{4}))", text, re.DOTALL)
        if not date_match:
            print(f"  [錯誤] 無法在文件中找到 'Advice sending date'")
            return None
        
        year_short = date_match.group(2)[-2:]  # 取完整年份的後兩位
        extracted_info['year'] = year_short
        print(f"  > 找到年份: {year_short}")

        # --- 2. 提取 Outlet 資訊 (BENE, CODE, OUTLETNUM) ---
        # 尋找主表格中的第一個條目
        # 格式: "1208008138/ APC-IT801", "1208008138 / APC-IT801", "1208008138/ APC - IT801"
        outlet_match = re.search(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)", text)
        if not outlet_match:
            print(f"  [錯誤] 無法找到 'Outlet no. / Name' 模式 (例如: 1208008138/ APC-IT801 或 1208008138/ APC - IT801)")
            return None
            
        extracted_info['outlet_num'] = outlet_match.group(1)
        extracted_info['bene_abbr'] = outlet_match.group(2)
        extracted_info['outlet_code'] = outlet_match.group(3)
        
        print(f"  > 找到 Outlet 號碼: {extracted_info['outlet_num']}")
        print(f"  > 找到受益人縮寫: {extracted_info['bene_abbr']}")
        print(f"  > 找到 Outlet 代碼: {extracted_info['outlet_code']}")

        return extracted_info

    def generate_new_filename(self, extracted_info, period_code):
        """
        根據提取的資訊生成新檔名
        
        Args:
            extracted_info (dict): 提取的資訊
            period_code (str): 期間代碼 (例如 P1, P2X)
            
        Returns:
            str: 新的檔案名稱
        """
        if not extracted_info:
            return None
            
        # 格式: YY_PX_BENE_CODE_OUTLETNUM.pdf
        new_filename = (
            f"{extracted_info['year']}_"
            f"{period_code}_"
            f"{extracted_info['bene_abbr']}_"
            f"{extracted_info['outlet_code']}_"
            f"{extracted_info['outlet_num']}.pdf"
        )
        
        return new_filename

    def rename_single_file_with_prompt(self, pdf_path):
        """
        重新命名單一 PDF 檔案 (會自動詢問期間代碼)
        
        Args:
            pdf_path (str): PDF 檔案路徑
            
        Returns:
            bool: 是否成功重新命名
        """
        print(f"準備處理檔案: {os.path.basename(pdf_path)}")
        period_code = self.get_period_code_from_user()
        return self.rename_single_file(pdf_path, period_code)

    def rename_single_file(self, pdf_path, period_code):
        """
        重新命名單一 PDF 檔案
        
        Args:
            pdf_path (str): PDF 檔案路徑
            period_code (str): 期間代碼
            
        Returns:
            bool: 是否成功重新命名
        """
        print(f"\n--- 處理檔案: {os.path.basename(pdf_path)} ---")
        
        # 提取 PDF 資訊
        extracted_info = self.extract_pdf_info(pdf_path)
        if not extracted_info:
            return False
            
        # 生成新檔名
        new_filename = self.generate_new_filename(extracted_info, period_code)
        if not new_filename:
            print(f"  [錯誤] 無法生成新檔名")
            return False
            
        # 建立新的完整路徑
        directory = os.path.dirname(pdf_path)
        new_filepath = os.path.join(directory, new_filename)
        
        # 檢查檔案是否已存在
        if os.path.exists(new_filepath):
            print(f"  [警告] 檔案 '{new_filename}' 已存在，跳過重新命名")
            return False
            
        # 執行重新命名
        original_filename = os.path.basename(pdf_path)
        print(f"  > 重新命名 '{original_filename}' 為 '{new_filename}'")
        
        try:
            os.rename(pdf_path, new_filepath)
            print("  > 重新命名成功！")
            return True
        except Exception as e:
            print(f"  [錯誤] 重新命名失敗。原因: {e}")
            return False

    def batch_rename(self, folder_path, period_code):
        """
        批量重新命名資料夾中的所有 PDF 檔案
        
        Args:
            folder_path (str): 資料夾路徑
            period_code (str): 期間代碼
            
        Returns:
            dict: 處理結果統計
        """
        folder_path = Path(folder_path)
        
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"[嚴重錯誤] 資料夾 '{folder_path}' 不存在或不是有效目錄")
            return {'success': 0, 'failed': 0, 'total': 0}
            
        print(f"\n--- 處理資料夾中的所有 PDF: {folder_path} ---")
        
        # 尋找所有 PDF 檔案
        pdf_files = list(folder_path.glob("*.pdf"))
        
        if not pdf_files:
            print("  [資訊] 在資料夾中未找到 PDF 檔案")
            return {'success': 0, 'failed': 0, 'total': 0}
            
        print(f"  [資訊] 找到 {len(pdf_files)} 個 PDF 檔案")
        
        # 處理每個檔案
        success_count = 0
        failed_count = 0
        
        for pdf_file in pdf_files:
            if self.rename_single_file(str(pdf_file), period_code):
                success_count += 1
            else:
                failed_count += 1
                
        print(f"\n--- 處理完成 ---")
        print(f"成功: {success_count} 個檔案")
        print(f"失敗: {failed_count} 個檔案")
        print(f"總計: {len(pdf_files)} 個檔案")
        
        return {
            'success': success_count,
            'failed': failed_count,
            'total': len(pdf_files)
        }

    def get_period_code_from_user(self):
        """從用戶獲取期間代碼"""
        print("請選擇期間代碼設定方式：")
        print("1. 輸入數字 (例如：輸入 1 會產生 P1)")
        print("2. 直接輸入完整期間代碼 (例如：P1, P2X)")
        
        choice = input("請選擇 (1 或 2): ").strip()
        
        if choice == "1":
            # 數字模式
            while True:
                try:
                    number = input("請輸入期間數字 (例如：1, 2, 3): ").strip()
                    if not number:
                        print("期間數字不能為空，請重新輸入。")
                        continue
                    
                    # 驗證是否為數字
                    int(number)  # 這會拋出異常如果不是數字
                    period_code = f"P{number}"
                    
                    # 確認期間代碼
                    print(f"生成的期間代碼: {period_code}")
                    confirm = input("確認使用此期間代碼嗎？(y/n): ").strip().lower()
                    if confirm in ['y', 'yes', '是', '確認']:
                        return period_code
                    
                except ValueError:
                    print("請輸入有效的數字。")
                    
        else:
            # 直接輸入模式
            while True:
                period_code = input("請輸入完整期間代碼 (例如 P1, P2X): ").strip()
                if not period_code:
                    print("期間代碼不能為空，請重新輸入。")
                    continue
                    
                # 簡單驗證期間代碼格式
                if not period_code.upper().startswith('P'):
                    print("期間代碼應該以 'P' 開頭，例如 P1, P2X")
                    continue
                    
                return period_code.upper()

    def interactive_mode(self):
        """互動模式：讓使用者選擇資料夾和期間代碼"""
        print("=== HSBC Payment Advice PDF 重新命名工具 ===")
        print("此工具會自動提取 PDF 中的資訊並重新命名檔案")
        print("命名格式: YY_PX_BENE_CODE_OUTLETNUM.pdf\n")
        
        # 獲取期間代碼
        period_code = self.get_period_code_from_user()
        
        # 獲取資料夾路徑
        folder_path = ""
        while not folder_path or not os.path.isdir(folder_path):
            folder_path = input("請輸入包含 PDF 檔案的資料夾路徑: ").strip()
            if not folder_path:
                print("路徑不能為空，請重新輸入。")
            elif not os.path.isdir(folder_path):
                print(f"路徑 '{folder_path}' 不是有效的資料夾，請重新輸入。")
        
        # 執行批量重新命名
        return self.batch_rename(folder_path, period_code)


def main():
    """主程式"""
    parser = argparse.ArgumentParser(description="HSBC Payment Advice PDF 重新命名工具")
    parser.add_argument("-d", "--directory", help="包含 PDF 檔案的目錄路徑")
    parser.add_argument("-p", "--period", help="期間代碼 (例如 P1, P2X)")
    parser.add_argument("-f", "--file", help="單一 PDF 檔案路徑")
    parser.add_argument("-i", "--interactive", action="store_true", 
                       help="啟動互動模式")
    parser.add_argument("--auto", action="store_true",
                       help="自動處理當前目錄的 PDF 檔案 (會詢問期間代碼)")
    
    args = parser.parse_args()
    
    # 建立重新命名工具
    renamer = HSBCPaymentAdviceRenamer()
    
    # 自動模式：處理當前目錄的 PDF 檔案
    if args.auto:
        current_dir = os.getcwd()
        pdf_files = [f for f in os.listdir(current_dir) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            print("當前目錄中沒有找到 PDF 檔案")
            return
            
        print(f"在當前目錄找到 {len(pdf_files)} 個 PDF 檔案:")
        for pdf in pdf_files:
            print(f"  - {pdf}")
        
        # 獲取期間代碼
        period_code = renamer.get_period_code_from_user()
        
        # 處理每個檔案
        print(f"\n開始使用期間代碼 '{period_code}' 處理檔案...")
        for pdf_file in pdf_files:
            full_path = os.path.join(current_dir, pdf_file)
            renamer.rename_single_file(full_path, period_code)
        return
    
    # 互動模式
    if args.interactive or (not args.directory and not args.file):
        renamer.interactive_mode()
        return
    
    # 檢查是否提供期間代碼（單檔案或目錄模式需要）
    if not args.period and (args.file or args.directory):
        print("[錯誤] 請提供期間代碼 (使用 -p 或 --period)，或使用 --auto 模式自動詢問")
        return
    
    # 處理單一檔案
    if args.file:
        if not os.path.exists(args.file):
            print(f"[錯誤] 檔案 '{args.file}' 不存在")
            return
        renamer.rename_single_file(args.file, args.period)
    
    # 處理整個目錄
    elif args.directory:
        renamer.batch_rename(args.directory, args.period)
    
    else:
        print("請提供 --directory、--file、--auto 或使用 --interactive 模式")
        print("使用 -h 或 --help 查看完整選項")


if __name__ == "__main__":
    main()
