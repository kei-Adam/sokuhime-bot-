import os
import re
import sys
import time
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv
from linebot import LineBotApi
from linebot.models import TextSendMessage
from playwright.sync_api import sync_playwright

# 環境変数の読み込み
load_dotenv()

CTI_URL = os.getenv("CTI_URL", "https://cti2.fuzoku-fan.jp/top/#login/staff?officeId=4fPMNw&apiKey=M45w5LiGupcJ")
CTI_PASS = os.getenv("CTI_PASS", "4Nq1rDR0")

SH_STORES = [
    {
        "name": os.getenv("STORE_1_NAME", "ド変態妄想MANIA"),
        "id": os.getenv("STORE_1_ID", "1710056980"),
        "pass": os.getenv("STORE_1_PASS", "d9im80sa")
    },
    {
        "name": os.getenv("STORE_2_NAME", "王様の秘密部屋"),
        "id": os.getenv("STORE_2_ID", "1710055945"),
        "pass": os.getenv("STORE_2_PASS", "k9gt45oo")
    }
]

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def get_cti_records():
    """
    CTIから出勤キャストの状況を取得し、レコードのリストを返す。
    「あやの,あや」表記を展開し、names配列を持たせる。
    """
    print(f">> [1/3] CTIv2から出勤状況を取得中...")
    records = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            page.goto(CTI_URL)
            page.wait_for_selector('#password', timeout=30000)
            page.fill('#password', CTI_PASS)
            page.click('button.login-btn')
            page.wait_for_selector('.hime-name', timeout=60000)
            time.sleep(5)

            for name_el in page.query_selector_all('.hime-name'):
                try:
                    raw_name = name_el.inner_text().strip()
                    names = [n.strip() for n in raw_name.split(',') if n.strip()]
                    if not names:
                        continue

                    row = name_el.evaluate_handle("el => el.closest('.hime-col') || el.parentElement")
                    row_el = row.as_element()
                    time_el = row_el.query_selector('.hime-time')
                    status_text = time_el.inner_text().strip() if time_el else ""
                    row_text = row_el.inner_text()

                    is_off = "お休み" in row_text or "休み" in row_text
                    if is_off:
                        continue  # お休みのキャストは全体同期の計算から除外

                    match = re.search(r'(\d{1,2}:\d{2})', status_text)
                    start_time_str = match.group(1) if match else None
                    is_closed = "受" in status_text or "Up" in status_text

                    record = {
                        "names": names,
                        "raw_name": raw_name,
                        "status_text": status_text,
                        "start_time": start_time_str,
                        "is_closed": is_closed
                    }
                    records.append(record)
                    print(f"   - 出勤キャスト検出: {names} | 状況: {status_text}")
                except Exception as inner_e:
                    pass
        except Exception as e:
            print(f"   [エラー] CTI取得失敗: {e}")
            traceback.print_exc()
        finally:
            browser.close()
    return records


def calculate_next_time(cast_info):
    """
    次回受付時間または 'now' を算出する。
    """
    now = datetime.now()
    if not cast_info["is_closed"]:
        return "now"
    if cast_info["start_time"]:
        try:
            start_h, start_m = map(int, cast_info["start_time"].split(":"))
            start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            if now >= start_dt:
                return "05:30"
            else:
                target_dt = start_dt - timedelta(minutes=5)
                return target_dt.strftime("%H:%M")
        except:
            return "05:30"
    return "05:30"


def update_all_stores():
    """
    全店舗のシティヘブンに順次ログインし、取得したCTIレコードに基づき全対象キャストを一括更新する。
    戻り値: サマリー結果の文字列リスト
    """
    records = get_cti_records()
    if not records:
        return ["[中断] 出勤中のキャストが見つからないか、CTIデータの取得に失敗しました。"]

    # 更新対象リストの組み立て
    update_targets = []
    for rec in records:
        t_time = calculate_next_time(rec)
        update_targets.append({"record": rec, "target_time": t_time})

    print(f"\n>> [2/3] 全 {len(update_targets)} 名の出勤キャストの即姫情報一括同期を開始します。")
    results = []

    for store in SH_STORES:
        print(f"\n>> シティヘブン同期中: {store['name']}")
        store_results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.set_default_timeout(120000)
            try:
                # ログイン
                page.goto("https://newmanager.cityheaven.net/", wait_until="load")
                page.wait_for_selector('#id:visible', timeout=60000).fill(store["id"])
                page.fill('#pass:visible', store["pass"])
                time.sleep(2)
                page.click('button:visible')

                page.wait_for_selector('a:has-text("TOP"), #logo', timeout=60000)
                time.sleep(5)

                cast_menu = page.query_selector('a:has-text("キャスト")')
                if cast_menu:
                    cast_menu.click()
                    time.sleep(2)

                sokuhime_link = page.query_selector('a:has-text("即ヒメ登録")')
                if sokuhime_link:
                    href = sokuhime_link.get_attribute("href")
                    if href and href != "#" and not href.startswith("javascript"):
                        print(f"   即ヒメ登録のURLを検出: {href} (直接遷移します)")
                        target_url = href if href.startswith("http") else f"https://newmanager.cityheaven.net/{href.lstrip('/')}"
                        page.goto(target_url, wait_until="load")
                    else:
                        print("   別タブで開く挙動を監視してクリックします...")
                        with context.expect_page() as new_page_info:
                            sokuhime_link.click()
                        page = new_page_info.value
                else:
                    page.click('a:has-text("即ヒメ登録")')

                time.sleep(5)
                # キャスト一覧枠（.sokuhimebox）が表示されるまで待機
                page.wait_for_selector('.sokuhimebox', timeout=60000)
                time.sleep(3)

                boxes = page.query_selector_all('.sokuhimebox')
                print(f"   {len(boxes)}名の登録枠を確認。CTIレコードと照合します...")

                for box in boxes:
                    box_text = box.inner_text()
                    matched_target = None
                    matched_name_in_box = None

                    # このコンテナ名に合致するCTIターゲットを探す
                    for target in update_targets:
                        for name in target["record"]["names"]:
                            if name in box_text:
                                matched_target = target
                                matched_name_in_box = name
                                break
                        if matched_target:
                            break

                    if not matched_target:
                        continue

                    t_time = matched_target["target_time"]
                    if t_time == "now":
                        print(f"   ・{matched_name_in_box} -> 待機中＆即ヒメボタン押下")
                        # 待機中ボタン (.waitingUpdate または img[alt="待機中"])
                        wait_btn = box.query_selector('.waitingUpdate, img[alt="待機中"], a:has-text("待機中")')
                        if wait_btn:
                            wait_btn.scroll_into_view_if_needed()
                            wait_btn.click()
                            time.sleep(2)
                        
                        # 即姫ボタン (.sokuhimeUpdate または img[alt="即ヒメ"])
                        sokuhime_btn = box.query_selector('.sokuhimeUpdate, img[alt="即ヒメ"]')
                        if sokuhime_btn:
                            sokuhime_btn.scroll_into_view_if_needed()
                            # 既にON（sokuhime_on）の場合は押さない（解除防止）
                            src = sokuhime_btn.get_attribute("src") or ""
                            if "sokuhime_off" in src:
                                sokuhime_btn.click()
                                time.sleep(1)
                        store_results.append(f"{matched_name_in_box} (待機中/即姫)")
                    else:
                        print(f"   ・{matched_name_in_box} -> 次回受付: {t_time}")
                        # 接客中/次回受付ボタン (.servingEndTimeUpdate または img[alt="接客中"])
                        serving_btn = box.query_selector('.servingEndTimeUpdate, .servingEndTime, img[alt="接客中"]')
                        if serving_btn:
                            serving_btn.scroll_into_view_if_needed()
                            serving_btn.click()
                            time.sleep(2)
                            # ポップアップ内のセレクトボックス
                            if page.query_selector('#servingEndHourList'):
                                h, m = t_time.split(":")
                                page.select_option('#servingEndHourList', value=h)
                                page.select_option('#servingEndMinuteList', value=m)
                                # OKボタン
                                page.click('input[name="ok"], #popup_ok, button:has-text("OK")')
                        store_results.append(f"{matched_name_in_box} (次回受付:{t_time})")
                    time.sleep(2)

                if store_results:
                    results.append(f"【{store['name']}】\n" + " / ".join(store_results))
                else:
                    results.append(f"【{store['name']}】\n更新対象なし")

            except Exception as e:
                print(f"   [エラー] {store['name']} 同期失敗: {e}")
                traceback.print_exc()
                results.append(f"【{store['name']}】\n同期エラー発生")
            finally:
                browser.close()

    return results


def send_line_notification(summary_results):
    """
    LINE Messaging APIを用いて更新結果をプッシュ通知する。
    """
    channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    # 通知先ユーザーID（またはグループID）。環境変数またはActionsの実行引数から取得
    notify_target_id = os.getenv("LINE_NOTIFY_TARGET_ID", "")

    if not channel_access_token or not notify_target_id:
        print("\n[通知スキップ] LINE認証情報または通知先IDが設定されていないため、LINE通知は行いません。")
        return

    print(f"\n>> [3/3] LINEへ結果通知を送信します (宛先: {notify_target_id})...")
    try:
        line_bot_api = LineBotApi(channel_access_token)
        message_text = "【即姫 全体一括同期完了】\n予約状況に基づき、出勤キャストの即姫情報を反映しました。\n\n" + "\n\n".join(summary_results)
        line_bot_api.push_message(notify_target_id, TextSendMessage(text=message_text))
        print("   完了: LINE通知を送信しました。")
    except Exception as e:
        print(f"   [エラー] LINE通知送信失敗: {e}")


if __name__ == "__main__":
    print(f"=== 即姫全体一括同期バッチ 実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    res = update_all_stores()
    print("\n=== 実行サマリー ===")
    for r in res:
        print(r)
    send_line_notification(res)
    print("=== すべての工程が完了しました ===")
