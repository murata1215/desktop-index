# Desktop Index

🔍 Google Desktop風のローカルファイル検索システム

ローカルディスクやネットワークドライブのファイルをクロールし、全文検索を可能にするWebアプリケーションです。

## 特徴

- **高速な全文検索** - Meilisearchによるミリ秒単位の検索
- **ドキュメント内容検索** - PDF、Word、Excel、テキストファイルの中身も検索可能
- **日本語対応** - 日本語ファイル名・内容を正しく検索
- **タイポ耐性** - 多少の入力ミスでも検索可能
- **Web UI** - ブラウザからアクセスできるシンプルな検索画面
- **定期スキャン** - バックグラウンドで定期的にファイルを巡回・更新
- **Docker対応** - docker-compose一発で起動

## スクリーンショット

```
┌─────────────────────────────────────────┐
│  🔍 Desktop Index                        │
│                                         │
│  ローカルファイルを高速検索              │
│                                         │
│  [________________検索________________]  │
│                                         │
│  📄 PDF  📝 Word  📊 Excel  📃 テキスト │
└─────────────────────────────────────────┘
```

## 必要環境

- Docker Desktop for Windows
- 検索対象のドライブへのアクセス権限

## クイックスタート

### 1. 設定ファイルの編集

#### docker-compose.yml

検索対象フォルダをボリュームマウントに追加します：

```yaml
volumes:
  # Windows のドライブをマウント
  - C:/Users:/mnt/c_users:ro
  - D:/:/mnt/d_drive:ro
  # ネットワークドライブ（事前にWindowsでマウント済みであること）
  - Z:/:/mnt/network_share:ro
```

#### config.yaml

マウントしたパスをスキャン対象に設定します：

```yaml
scan_paths:
  - /mnt/c_users
  - /mnt/d_drive
  - /mnt/network_share
```

### 2. 起動

```bash
docker-compose up -d
```

### 3. アクセス

ブラウザで http://localhost:8000 を開きます。

## 使い方

### 検索

1. トップページの検索ボックスにキーワードを入力
2. Enter または「検索」ボタンをクリック
3. 検索結果からファイルパスをクリックしてコピー
4. エクスプローラーでファイルを開く

### フィルター検索

検索結果ページで拡張子フィルターを使用できます：
- PDF、Word、Excel、テキストなどで絞り込み

### ステータス確認

http://localhost:8000/status でシステム状態を確認できます：
- インデックス済みファイル数
- クローラーの実行状態
- 次回スキャン予定

## 設定詳細

### config.yaml

| 設定項目 | 説明 | デフォルト値 |
|---------|------|-------------|
| `scan_paths` | スキャン対象ディレクトリ | `/mnt/c_users` |
| `exclude_patterns` | 除外パターン（ワイルドカード対応） | `*.tmp`, `node_modules` 等 |
| `supported_extensions` | インデックス対象の拡張子 | `.pdf`, `.docx`, `.xlsx` 等 |
| `scan_interval_minutes` | スキャン間隔（分） | `60` |
| `batch_size` | バッチ登録サイズ | `1000` |
| `max_file_size_mb` | 内容抽出の最大ファイルサイズ | `50` MB |
| `max_content_length` | 抽出テキストの最大長 | `100000` 文字 |

### 除外パターン例

```yaml
exclude_patterns:
  # 一時ファイル
  - "*.tmp"
  - "~$*"

  # システムフォルダ
  - "Windows"
  - "$RECYCLE.BIN"

  # 開発関連
  - "node_modules"
  - ".git"
  - "__pycache__"
```

## 対応ファイル形式

### 内容検索対応

| 形式 | 拡張子 | 備考 |
|-----|-------|------|
| PDF | `.pdf` | テキストベースのPDFのみ（画像PDFは非対応） |
| Word | `.docx` | 旧形式（.doc）は非対応 |
| Excel | `.xlsx` | 旧形式（.xls）は非対応 |
| テキスト | `.txt`, `.md`, `.csv` | エンコーディング自動検出 |
| ソースコード | `.py`, `.js`, `.ts` 等 | 多数対応 |

### ファイル名のみ検索

上記以外の拡張子はファイル名とパスのみが検索対象になります。

## API

REST APIも利用可能です：

| エンドポイント | メソッド | 説明 |
|--------------|---------|------|
| `/api/search?q=キーワード` | GET | 全文検索 |
| `/api/stats` | GET | 統計情報取得 |
| `/api/crawl/start` | POST | クロール開始 |
| `/api/crawl/stop` | POST | クロール停止 |
| `/api/crawl/status` | GET | クロール状態取得 |
| `/api/index/clear` | POST | インデックスクリア |
| `/api/health` | GET | ヘルスチェック |

### 検索APIの例

```bash
# 基本検索
curl "http://localhost:8000/api/search?q=議事録"

# 拡張子フィルター
curl "http://localhost:8000/api/search?q=報告書&extension=.pdf"

# ソート
curl "http://localhost:8000/api/search?q=設計&sort=modified_at:desc"
```

## トラブルシューティング

### 検索結果が表示されない

1. ステータスページでインデックス済みファイル数を確認
2. クローラーが実行中か確認
3. `docker-compose logs app` でエラーを確認

### ネットワークドライブが見えない

1. WindowsでネットワークドライブをZドライブ等にマウント
2. Docker Desktop の設定で該当ドライブを共有
3. `docker-compose.yml` にボリュームマウントを追加

### 初回スキャンが遅い

数百万ファイルの初回スキャンには数時間かかる場合があります。
- CPU負荷を抑えながらバックグラウンドで実行されます
- ステータスページで進捗を確認できます

### 日本語が検索できない

Meilisearchは日本語対応済みですが、以下を確認してください：
- ファイルのエンコーディングがUTF-8またはShift_JIS
- PDFがテキストベースであること（画像PDFはOCR非対応）

## 開発

### ローカル開発

```bash
# 仮想環境を作成
python -m venv venv
venv\Scripts\activate

# 依存パッケージをインストール
pip install -r requirements.txt

# Meilisearchを起動（別ターミナル）
docker run -p 7700:7700 getmeili/meilisearch:v1.6

# アプリケーションを起動
uvicorn src.main:app --reload
```

### ディレクトリ構成

```
desktopindex/
├── docker-compose.yml    # Docker Compose設定
├── Dockerfile           # Dockerイメージ定義
├── requirements.txt     # Python依存パッケージ
├── config.yaml         # アプリケーション設定
├── src/
│   ├── main.py        # FastAPIエントリーポイント
│   ├── config.py      # 設定管理
│   ├── crawler/       # ファイルクローラー
│   │   ├── scanner.py    # ファイルスキャン
│   │   ├── parser.py     # ドキュメント解析
│   │   └── scheduler.py  # 定期実行
│   ├── indexer/       # インデクサー
│   │   └── meilisearch_client.py
│   ├── api/           # REST API
│   │   └── routes.py
│   └── web/           # Web UI
│       ├── templates/
│       └── static/
└── data/              # データ永続化
```

## ライセンス

MIT License

## 謝辞

- [Meilisearch](https://www.meilisearch.com/) - 高速な全文検索エンジン
- [FastAPI](https://fastapi.tiangolo.com/) - モダンなPython Webフレームワーク
- [pdfplumber](https://github.com/jsvine/pdfplumber) - PDF解析ライブラリ
