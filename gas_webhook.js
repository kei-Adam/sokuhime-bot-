/**
 * LINEボットから送信されたメッセージをトリガーとし、
 * GitHub Actionsのワークフロー (workflow_dispatch) を実行するGoogle Apps Script。
 * 
 * 【設定手順】
 * 1. Google Driveで「Google Apps Script」を新規作成し、このコードを貼り付けます。
 * 2. 以下の設定値（GITHUB_PAT, GITHUB_OWNER, GITHUB_REPO, LINE_ACCESS_TOKEN）を入力します。
 * 3. 右上の「デプロイ」>「新しいデプロイ」から「ウェブアプリ」を選択。
 * 4. アクセスできるユーザーを「全員」にしてデプロイし、発行されたURLをLINE DevelopersのWebhookに設定します。
 */

const GITHUB_PAT = "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN";
const GITHUB_OWNER = "YOUR_GITHUB_USERNAME_OR_ORG";
const GITHUB_REPO = "YOUR_REPOSITORY_NAME";
const WORKFLOW_FILE = "sokuhime_update.yml";

const LINE_ACCESS_TOKEN = "YOUR_LINE_CHANNEL_ACCESS_TOKEN";

function doPost(e) {
  try {
    const json = JSON.parse(e.postData.contents);
    const events = json.events;
    
    if (!events || events.length === 0) {
      return ContentService.createTextOutput("OK");
    }

    for (let i = 0; i < events.length; i++) {
      const event = events[i];
      if (event.type === "message" && event.message.type === "text") {
        const text = event.message.text.trim();
        const userId = event.source.userId;
        const replyToken = event.replyToken;

        // キーワード反応（例: 「即姫更新」が含まれていれば起動）
        if (text.includes("即姫更新")) {
          // 1. LINEユーザーへ即時応答
          replyToLine(replyToken, "予約状況を確認し、全店舗の即姫情報の一括更新をGitHub Actionsで開始します。\n反映完了後に改めて通知いたします。");
          
          // 2. GitHub ActionsのディスパッチAPIを呼び出し
          triggerGitHubAction(userId);
        }
      }
    }
  } catch (err) {
    console.error(err);
  }
  
  return ContentService.createTextOutput("OK");
}

function replyToLine(replyToken, messageText) {
  const url = "https://api.line.me/v2/bot/message/reply";
  const payload = {
    replyToken: replyToken,
    messages: [{ type: "text", text: messageText }]
  };
  
  const options = {
    method: "post",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + LINE_ACCESS_TOKEN
    },
    payload: JSON.stringify(payload)
  };
  
  UrlFetchApp.fetch(url, options);
}

function triggerGitHubAction(userId) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const payload = {
    ref: "main",
    inputs: {
      notify_user_id: userId
    }
  };

  const options = {
    method: "post",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": "Bearer " + GITHUB_PAT,
      "X-GitHub-Api-Version": "2022-11-28"
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(url, options);
  console.log("GitHub API Response: " + response.getContentText());
}
