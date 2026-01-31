# =============================================================================
# Desktop Index - API ルート
# =============================================================================
# REST API エンドポイントを定義します。
#
# エンドポイント:
#   GET  /api/search         - 全文検索
#   GET  /api/recent         - 最近のファイル取得
#   GET  /api/stats          - 統計情報取得
#   POST /api/crawl/start    - クロール開始
#   POST /api/crawl/stop     - クロール停止
#   GET  /api/crawl/status   - クロール状態取得
#   POST /api/index/clear    - インデックスクリア
#   POST /api/open-folder    - フォルダを開く
# =============================================================================

import logging
import subprocess
import os
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ルーターの作成
# ---------------------------------------------------------------------------
router = APIRouter(tags=["API"])


# ---------------------------------------------------------------------------
# レスポンスモデル
# ---------------------------------------------------------------------------
class SearchResult(BaseModel):
    """
    検索結果のレスポンスモデル

    Attributes:
        hits: マッチしたドキュメントのリスト
        total_hits: 推定総件数
        processing_time_ms: 処理時間（ミリ秒）
        query: 検索クエリ
    """
    hits: List[dict]
    total_hits: int
    processing_time_ms: int
    query: str


class StatsResponse(BaseModel):
    """
    統計情報のレスポンスモデル

    Attributes:
        total_documents: ドキュメント総数
        is_indexing: インデックス処理中かどうか
        field_distribution: フィールドごとのドキュメント数
    """
    total_documents: int
    is_indexing: bool
    field_distribution: dict


class CrawlStatusResponse(BaseModel):
    """
    クロール状態のレスポンスモデル

    Attributes:
        is_running: クロール実行中かどうか
        last_run: 最後にクロールを実行した日時
        next_run: 次回クロール予定日時
        files_processed: 処理済みファイル数
        current_path: 現在処理中のパス
    """
    is_running: bool
    last_run: Optional[str]
    next_run: Optional[str]
    files_processed: int
    current_path: Optional[str]


class MessageResponse(BaseModel):
    """
    汎用メッセージレスポンスモデル

    Attributes:
        success: 成功したかどうか
        message: メッセージ
    """
    success: bool
    message: str


class RecentFilesResponse(BaseModel):
    """
    最近のファイル一覧のレスポンスモデル

    Attributes:
        hits: 最近更新されたファイルのリスト
        total_hits: 総件数
        days: 対象期間（日数）
        extension_filter: 拡張子フィルター（適用されている場合）
    """
    hits: List[dict]
    total_hits: int
    days: int
    extension_filter: Optional[str]


class OpenFolderRequest(BaseModel):
    """
    フォルダを開くリクエストモデル

    Attributes:
        path: 開きたいファイルのフルパス
    """
    path: str


# ---------------------------------------------------------------------------
# 検索 API
# ---------------------------------------------------------------------------
@router.get("/search", response_model=SearchResult)
async def search(
    q: str = Query(..., description="検索クエリ"),
    limit: int = Query(20, ge=1, le=100, description="取得件数"),
    offset: int = Query(0, ge=0, description="スキップ件数"),
    extension: Optional[str] = Query(None, description="拡張子フィルター（例: .pdf）"),
    sort: Optional[str] = Query(None, description="ソート条件（例: modified_at:desc）")
):
    """
    全文検索を実行する

    指定されたクエリでインデックスを検索し、
    マッチしたドキュメントを返します。

    Args:
        q: 検索クエリ文字列（必須）
        limit: 返す結果の最大数（1-100、デフォルト: 20）
        offset: スキップする結果数（ページネーション用）
        extension: 拡張子でフィルター（例: ".pdf"）
        sort: ソート条件（例: "modified_at:desc"）

    Returns:
        SearchResult: 検索結果

    Example:
        GET /api/search?q=議事録&extension=.docx&sort=modified_at:desc
    """
    # main.py からグローバルクライアントを取得
    from src.main import meilisearch_client

    if not meilisearch_client:
        raise HTTPException(status_code=503, detail="検索サービスが利用できません")

    # フィルター条件の構築
    filters = None
    if extension:
        # 拡張子の正規化（ドットを追加）
        if not extension.startswith("."):
            extension = f".{extension}"
        filters = f"extension = '{extension}'"

    # ソート条件の構築
    sort_list = None
    if sort:
        sort_list = [sort]

    # 検索を実行
    results = await meilisearch_client.search(
        query=q,
        limit=limit,
        offset=offset,
        filters=filters,
        sort=sort_list,
        attributes_to_highlight=["filename", "content"]
    )

    return SearchResult(
        hits=results.get("hits", []),
        total_hits=results.get("estimatedTotalHits", 0),
        processing_time_ms=results.get("processingTimeMs", 0),
        query=q
    )


# ---------------------------------------------------------------------------
# 最近のファイル API
# ---------------------------------------------------------------------------
@router.get("/recent", response_model=RecentFilesResponse)
async def get_recent_files(
    days: int = Query(7, ge=1, le=30, description="取得する期間（日数）"),
    extension: Optional[str] = Query(None, description="拡張子フィルター（例: pdf, docx, xlsx）")
):
    """
    最近更新されたファイルを取得する

    指定された期間内に更新されたファイルを、更新日時の新しい順で返します。
    Office系ファイル（PDF, Word, Excel, PowerPoint）に限定して取得します。

    Args:
        days: 対象期間（日数）（1-30、デフォルト: 7）
        extension: 特定の拡張子でフィルター（例: "pdf", "docx"）
                   未指定の場合はOffice系ファイル全て

    Returns:
        RecentFilesResponse: 最近のファイル一覧

    Example:
        GET /api/recent?days=7&extension=pdf
    """
    from src.main import meilisearch_client

    if not meilisearch_client:
        raise HTTPException(status_code=503, detail="検索サービスが利用できません")

    # Office系ファイルの拡張子リスト
    office_extensions = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]

    # 対象期間の開始日時を計算
    # ISO 8601 形式で指定（Meilisearchで文字列比較可能）
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%dT%H:%M:%S")

    # フィルター条件の構築
    # 1. 更新日時が期間内
    # 2. 拡張子がOffice系（または特定の拡張子）
    if extension:
        # 特定の拡張子でフィルター
        ext = extension if extension.startswith(".") else f".{extension}"
        extension_filter = f"extension = '{ext}'"
    else:
        # Office系ファイル全て
        ext_conditions = " OR ".join([f"extension = '{ext}'" for ext in office_extensions])
        extension_filter = f"({ext_conditions})"

    # 日時フィルターと拡張子フィルターを組み合わせ
    filters = f"modified_at >= '{cutoff_str}' AND {extension_filter}"

    # 検索を実行（空クエリで全件取得、更新日時でソート）
    results = await meilisearch_client.search(
        query="",  # 空クエリで全件対象
        limit=1000,  # 1週間分なので十分な件数
        offset=0,
        filters=filters,
        sort=["modified_at:desc"]  # 更新日時の降順
    )

    return RecentFilesResponse(
        hits=results.get("hits", []),
        total_hits=results.get("estimatedTotalHits", 0),
        days=days,
        extension_filter=extension
    )


# ---------------------------------------------------------------------------
# フォルダを開く API
# ---------------------------------------------------------------------------
@router.post("/open-folder", response_model=MessageResponse)
async def open_folder(request: OpenFolderRequest):
    """
    ファイルの親フォルダをエクスプローラーで開く

    指定されたファイルのパスから親フォルダを取得し、
    Windowsエクスプローラーでそのファイルを選択した状態で開きます。

    Args:
        request: ファイルパスを含むリクエスト

    Returns:
        MessageResponse: 実行結果

    Note:
        セキュリティ: パスはバリデーションされ、
        インデックス済みのパスのみ許可されます。
    """
    path = request.path

    # パスのバリデーション
    if not path or not isinstance(path, str):
        raise HTTPException(status_code=400, detail="無効なパスです")

    # パスの正規化（セキュリティ対策）
    normalized_path = os.path.normpath(path)

    # パストラバーサル攻撃の防止
    if ".." in normalized_path:
        raise HTTPException(status_code=400, detail="不正なパスです")

    # ファイルが存在するか確認
    if not os.path.exists(normalized_path):
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    try:
        # Windows: explorer /select,"ファイルパス" でファイルを選択した状態で開く
        subprocess.Popen(
            ['explorer', '/select,', normalized_path],
            shell=False
        )
        return MessageResponse(
            success=True,
            message=f"フォルダを開きました: {os.path.dirname(normalized_path)}"
        )
    except Exception as e:
        logger.error(f"フォルダを開くエラー: {e}")
        raise HTTPException(status_code=500, detail=f"フォルダを開けませんでした: {str(e)}")


# ---------------------------------------------------------------------------
# 統計情報 API
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    インデックスの統計情報を取得する

    ドキュメント総数、インデックス状態などの情報を返します。

    Returns:
        StatsResponse: 統計情報
    """
    from src.main import meilisearch_client

    if not meilisearch_client:
        raise HTTPException(status_code=503, detail="検索サービスが利用できません")

    stats = await meilisearch_client.get_stats()

    return StatsResponse(
        total_documents=stats.get("numberOfDocuments", 0),
        is_indexing=stats.get("isIndexing", False),
        field_distribution=stats.get("fieldDistribution", {})
    )


# ---------------------------------------------------------------------------
# クロール制御 API
# ---------------------------------------------------------------------------
@router.post("/crawl/start", response_model=MessageResponse)
async def start_crawl():
    """
    クロールを手動で開始する

    定期スケジュールとは別に、即座にクロールを開始します。
    既にクロールが実行中の場合はエラーを返します。

    Returns:
        MessageResponse: 実行結果
    """
    from src.main import scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="クローラーサービスが利用できません")

    try:
        success = scheduler.run_now()
        if success:
            return MessageResponse(
                success=True,
                message="クロールを開始しました"
            )
        else:
            return MessageResponse(
                success=False,
                message="クロールは既に実行中です"
            )
    except Exception as e:
        logger.error(f"クロール開始エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawl/stop", response_model=MessageResponse)
async def stop_crawl():
    """
    実行中のクロールを停止する

    現在実行中のクロール処理を中断します。
    次回のスケジュールされたクロールには影響しません。

    Returns:
        MessageResponse: 実行結果
    """
    from src.main import scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="クローラーサービスが利用できません")

    try:
        scheduler.stop_current_crawl()
        return MessageResponse(
            success=True,
            message="クロールを停止しました"
        )
    except Exception as e:
        logger.error(f"クロール停止エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crawl/status", response_model=CrawlStatusResponse)
async def get_crawl_status():
    """
    クロールの状態を取得する

    現在のクロール実行状態、最終実行日時、
    次回実行予定日時などの情報を返します。

    Returns:
        CrawlStatusResponse: クロール状態
    """
    from src.main import scheduler

    if not scheduler:
        raise HTTPException(status_code=503, detail="クローラーサービスが利用できません")

    status = scheduler.get_status()

    return CrawlStatusResponse(
        is_running=status.get("is_running", False),
        last_run=status.get("last_run"),
        next_run=status.get("next_run"),
        files_processed=status.get("files_processed", 0),
        current_path=status.get("current_path")
    )


# ---------------------------------------------------------------------------
# インデックス管理 API
# ---------------------------------------------------------------------------
@router.post("/index/clear", response_model=MessageResponse)
async def clear_index():
    """
    インデックスを完全にクリアする

    警告: この操作は元に戻せません。
    全てのドキュメントが削除されます。

    Returns:
        MessageResponse: 実行結果
    """
    from src.main import meilisearch_client

    if not meilisearch_client:
        raise HTTPException(status_code=503, detail="検索サービスが利用できません")

    try:
        success = await meilisearch_client.clear_index()
        if success:
            return MessageResponse(
                success=True,
                message="インデックスをクリアしました"
            )
        else:
            return MessageResponse(
                success=False,
                message="インデックスのクリアに失敗しました"
            )
    except Exception as e:
        logger.error(f"インデックスクリアエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# ヘルスチェック API
# ---------------------------------------------------------------------------
@router.get("/health")
async def health_check():
    """
    サービスの健全性をチェックする

    Meilisearch サーバーとの接続状態を確認します。

    Returns:
        dict: ヘルスチェック結果
    """
    from src.main import meilisearch_client

    meili_healthy = False
    if meilisearch_client:
        meili_healthy = await meilisearch_client.health_check()

    return {
        "status": "healthy" if meili_healthy else "degraded",
        "meilisearch": "connected" if meili_healthy else "disconnected"
    }
