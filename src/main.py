# =============================================================================
# Desktop Index - FastAPI メインエントリーポイント
# =============================================================================
# アプリケーションの起動、ルーティング設定、バックグラウンドタスクの
# 初期化を行うメインモジュールです。
#
# 起動方法:
#   uvicorn src.main:app --host 0.0.0.0 --port 8000
# =============================================================================

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.api.routes import router as api_router
from src.crawler.scheduler import CrawlerScheduler
from src.indexer.meilisearch_client import MeilisearchClient


# ---------------------------------------------------------------------------
# ログ設定
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.logging.level),
    format=settings.logging.format
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# グローバルインスタンス
# ---------------------------------------------------------------------------
# スケジューラーとMeilisearchクライアントはアプリケーション全体で共有
scheduler: CrawlerScheduler = None
meilisearch_client: MeilisearchClient = None


# ---------------------------------------------------------------------------
# ライフサイクル管理
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPIアプリケーションのライフサイクルを管理する

    起動時の処理:
    1. Meilisearchクライアントの初期化
    2. インデックスの作成（存在しない場合）
    3. クローラースケジューラーの起動

    終了時の処理:
    1. スケジューラーの停止
    2. リソースのクリーンアップ

    Args:
        app: FastAPIアプリケーションインスタンス

    Yields:
        None: コンテキスト内でアプリケーションが実行される
    """
    global scheduler, meilisearch_client

    logger.info("=" * 60)
    logger.info("Desktop Index を起動しています...")
    logger.info("=" * 60)

    # Meilisearchクライアントの初期化
    logger.info(f"Meilisearch に接続中: {settings.meilisearch.host}")
    meilisearch_client = MeilisearchClient(
        host=settings.meilisearch.host,
        api_key=settings.meilisearch.api_key,
        index_name=settings.meilisearch.index_name
    )

    # インデックスの初期化（存在しない場合は作成）
    await meilisearch_client.initialize_index()
    logger.info("Meilisearch インデックスの準備が完了しました")

    # クローラースケジューラーの初期化と起動
    scheduler = CrawlerScheduler(
        meilisearch_client=meilisearch_client,
        scan_paths=settings.scan_paths,
        exclude_patterns=settings.exclude_patterns,
        supported_extensions=settings.supported_extensions,
        interval_minutes=settings.scan_interval_minutes,
        batch_size=settings.batch_size,
        max_file_size_mb=settings.max_file_size_mb,
        max_content_length=settings.max_content_length
    )
    scheduler.start()
    logger.info(f"クローラーを {settings.scan_interval_minutes} 分間隔で実行します")

    logger.info("=" * 60)
    logger.info("Desktop Index の起動が完了しました")
    logger.info("Web UI: http://localhost:8000")
    logger.info("=" * 60)

    # アプリケーション実行中
    yield

    # シャットダウン処理
    logger.info("Desktop Index を終了しています...")
    if scheduler:
        scheduler.stop()
    logger.info("Desktop Index を終了しました")


# ---------------------------------------------------------------------------
# FastAPIアプリケーションの作成
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Desktop Index",
    description="ローカルディスク・ネットワークドライブのファイル検索システム",
    version="1.0.0",
    lifespan=lifespan
)


# ---------------------------------------------------------------------------
# 静的ファイルとテンプレートの設定
# ---------------------------------------------------------------------------
# 静的ファイル（CSS、JavaScript）のディレクトリ
static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Jinja2テンプレートのディレクトリ
templates_dir = Path(__file__).parent / "web" / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# ---------------------------------------------------------------------------
# テンプレート用ヘルパー関数
# ---------------------------------------------------------------------------
def get_file_icon(extension: str) -> str:
    """
    ファイル拡張子に対応する絵文字アイコンを取得する

    Args:
        extension: ファイル拡張子（例: '.pdf'）

    Returns:
        str: 絵文字アイコン
    """
    icon_map = {
        '.pdf': '📕',
        '.doc': '📘',
        '.docx': '📘',
        '.xls': '📗',
        '.xlsx': '📗',
        '.ppt': '📙',
        '.pptx': '📙',
        '.txt': '📄',
        '.md': '📝',
        '.csv': '📊',
        '.json': '📋',
        '.py': '🐍',
        '.js': '📜',
        '.ts': '📜',
        '.html': '🌐',
        '.css': '🎨',
    }
    return icon_map.get(extension.lower(), '📄') if extension else '📄'


def format_file_size(size: int) -> str:
    """
    ファイルサイズを人間が読みやすい形式にフォーマットする

    Args:
        size: ファイルサイズ（バイト）

    Returns:
        str: フォーマットされたサイズ（例: '1.5 MB'）
    """
    if not size:
        return '不明'

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.1f} {units[unit_index]}"


# テンプレートにヘルパー関数を登録
templates.env.globals['get_file_icon'] = get_file_icon
templates.env.globals['format_file_size'] = format_file_size


# ---------------------------------------------------------------------------
# ルーターの登録
# ---------------------------------------------------------------------------
# APIルーター（検索、クロール制御など）を登録
app.include_router(api_router, prefix="/api")


# ---------------------------------------------------------------------------
# ルートエンドポイント（Web UI）
# ---------------------------------------------------------------------------
@app.get("/")
async def index(request: Request):
    """
    メインページ（検索UI）を表示する

    Args:
        request: FastAPIリクエストオブジェクト

    Returns:
        TemplateResponse: レンダリングされたHTMLページ
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Desktop Index"
        }
    )


@app.get("/search")
async def search_page(request: Request, q: str = ""):
    """
    検索結果ページを表示する

    クエリパラメータ q が指定されている場合は検索を実行し、
    結果を表示します。

    Args:
        request: FastAPIリクエストオブジェクト
        q: 検索クエリ文字列

    Returns:
        TemplateResponse: 検索結果を含むHTMLページ
    """
    results = []
    total_hits = 0
    processing_time_ms = 0

    if q:
        # 検索を実行
        search_result = await meilisearch_client.search(
            query=q,
            limit=50,
            attributes_to_highlight=["filename", "content"]
        )
        results = search_result.get("hits", [])
        total_hits = search_result.get("estimatedTotalHits", 0)
        processing_time_ms = search_result.get("processingTimeMs", 0)

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "title": f"検索: {q}" if q else "Desktop Index",
            "query": q,
            "results": results,
            "total_hits": total_hits,
            "processing_time_ms": processing_time_ms
        }
    )


@app.get("/status")
async def status_page(request: Request):
    """
    システムステータスページを表示する

    インデックスの状態、クローラーの状態、統計情報などを表示します。

    Args:
        request: FastAPIリクエストオブジェクト

    Returns:
        TemplateResponse: ステータス情報を含むHTMLページ
    """
    # インデックスの統計情報を取得
    stats = await meilisearch_client.get_stats()

    # スケジューラーの状態を取得
    scheduler_status = scheduler.get_status() if scheduler else {}

    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "title": "システムステータス",
            "index_stats": stats,
            "scheduler_status": scheduler_status,
            "settings": {
                "scan_paths": settings.scan_paths,
                "scan_interval_minutes": settings.scan_interval_minutes,
                "supported_extensions": settings.supported_extensions[:10],  # 最初の10個のみ表示
            }
        }
    )
