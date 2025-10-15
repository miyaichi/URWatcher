# URWatcher 🏙️
**UR賃貸物件の新着・削除を検知して通知するエージェント**

---

## 💡 概要
URWatcher は、UR都市機構の公式サイトに掲載される賃貸物件情報を定期的に監視し、
物件が **新たに追加された／削除された（満室になった）** ことを検知して Slack / LINE に通知する自動監視ツールです。

---

## 🚀 セットアップ

### 1️⃣ クローン
```bash
git clone https://github.com/miyaichi/urwatcher.git
cd urwatcher
```

### 2️⃣ 依存関係インストール
```bash
pip install -r requirements.txt
```

### 3️⃣ 通知設定
```
SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
LINE_NOTIFY_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4️⃣ 実行
```bash
python monitor_ur.py
```

---

## ⚙️ 設定項目
- `TARGET_URL`: 監視対象のエリアページ（未指定時は都内全体の一覧ページ）
- `DATABASE_URL`: SQLite などの接続先（未指定時は `sqlite:///ur_monitor.db`）
- `SLACK_WEBHOOK`: Slack Incoming Webhook URL（任意）
- `LINE_NOTIFY_TOKEN`: LINE Notify アクセストークン（任意）

---

## 📊 出力例（Slack / LINE通知）

```
:new: 新しい物件が追加されました
物件名: 東雲キャナルコートCODAN 3-4号棟
URL: https://www.ur-net.go.jp/chintai/kanto/tokyo/70_0000.html

:x: 掲載終了
物件名: 光が丘パークタウン春の風
```

---

## 🧪 ローカル開発 (Docker + SQLite)
- `Dockerfile.dev`（Python 3.11 slim ベース）で開発用イメージをビルドし、`docker compose` から起動
- ホスト側の `./data` をコンテナ内 `/app/data` にマウントし、`sqlite:///data/urwatcher.db` で監視履歴を永続化
- コードは `.:/app` をマウントして即時反映、Slack Webhook などは `.env` もしくは compose の `environment` で設定（不要ならダミー値）

### 参考 `docker-compose.yml`
```yaml
services:
  urwatcher:
    build:
      context: .
      dockerfile: Dockerfile.dev
    command: python monitor_ur.py --run
    environment:
      - SLACK_WEBHOOK=${SLACK_WEBHOOK:-}
      - LINE_NOTIFY_TOKEN=${LINE_NOTIFY_TOKEN:-}
      - DATABASE_URL=sqlite:///data/urwatcher.db
    volumes:
      - .:/app
      - ./data:/app/data
    tty: true
```

起動例:
```bash
docker compose run --rm urwatcher --init
docker compose run --rm urwatcher --run
docker compose run --rm urwatcher pytest
```

---

## 📝 運用メモ
- 初回 `--run` は全エリアを巡回するため時間が掛かりますが、以降はエリアページのハッシュを元に更新があったエリアのみスクレイプします（変更が無ければ `No new rooms detected` が表示されます）
- 全エリアを再スキャンしたい場合は `sqlite3 data/urwatcher.db "DELETE FROM area_snapshots;"` を実行後に `--run` してください
- 対象エリアを絞りたいときは `TARGET_URL` を個別のエリアページに設定すると高速に確認できます

---

## 📈 アーキテクチャ概要
```
[UR公式サイト] → [Scraper] → [差分比較] → [SQLite DB] → [通知(Slack / LINE)]
```

---

## 🔄 今後のリモート展開
- 現時点ではローカル Docker + SQLite 構成をベースに安定動作の検証を優先
- リモート環境（GitHub Actions + AWS など）へのデプロイはローカル運用が固まった段階で再検討し、必要なワークフローやインフラ構成を整備予定

---

## 🧩 開発情報
| 項目 | 内容 |
|------|------|
| 言語 | Python 3.11 |
| 依存 | requests, BeautifulSoup4, sqlite3 |
| 通知 | Slack Webhook / LINE Notify |
| DB | SQLite |
| ライセンス | MIT |
| 作者 | Yoshihiko Miyaichi |
