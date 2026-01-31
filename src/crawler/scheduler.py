# =============================================================================
# Desktop Index - クローラースケジューラー
# =============================================================================
# 定期的にファイルスキャンとインデックス更新を実行するスケジューラーです。
#
# 主な機能:
#   - 定期実行（設定可能な間隔）
#   - 手動実行トリガー
#   - CPU負荷を抑えた実行
#   - 実行状態の管理
# =============================================================================

import asyncio
import logging
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.crawler.scanner import FileScanner, FileInfo
from src.crawler.parser import DocumentParser
from src.indexer.meilisearch_client import MeilisearchClient

logger = logging.getLogger(__name__)


class CrawlerScheduler:
    """
    ファイルクローラーの定期実行を管理するスケジューラークラス

    このクラスは以下の機能を提供します:
    - 指定間隔での定期クロール実行
    - 手動でのクロール開始/停止
    - クロール状態の追跡と報告
    - CPU負荷を考慮した実行制御

    使用例:
        scheduler = CrawlerScheduler(
            meilisearch_client=client,
            scan_paths=["/mnt/c_users"],
            interval_minutes=60
        )
        scheduler.start()  # 定期実行を開始
        scheduler.run_now()  # 手動で即座に実行
        scheduler.stop()  # 停止

    Attributes:
        meilisearch_client: Meilisearch クライアント
        scan_paths: スキャン対象のディレクトリパスリスト
        interval_minutes: 定期実行の間隔（分）
    """

    def __init__(
        self,
        meilisearch_client: MeilisearchClient,
        scan_paths: List[str],
        exclude_patterns: List[str] = None,
        supported_extensions: List[str] = None,
        interval_minutes: int = 60,
        batch_size: int = 1000,
        max_file_size_mb: int = 50,
        max_content_length: int = 100000
    ):
        """
        CrawlerScheduler を初期化する

        Args:
            meilisearch_client: Meilisearch クライアントインスタンス
            scan_paths: スキャン対象のディレクトリパスリスト
            exclude_patterns: 除外するファイル/フォルダのパターン
            supported_extensions: インデックス対象の拡張子リスト
            interval_minutes: 定期実行の間隔（分）
            batch_size: Meilisearchへのバッチ登録サイズ
            max_file_size_mb: 内容抽出対象の最大ファイルサイズ（MB）
            max_content_length: 抽出テキストの最大長（文字数）
        """
        self.meilisearch_client = meilisearch_client
        self.scan_paths = scan_paths
        self.exclude_patterns = exclude_patterns or []
        self.supported_extensions = supported_extensions or []
        self.interval_minutes = interval_minutes
        self.batch_size = batch_size
        self.max_file_size_mb = max_file_size_mb
        self.max_content_length = max_content_length

        # スケジューラーの初期化
        self._scheduler = BackgroundScheduler()

        # 状態管理
        self._is_running = False
        self._stop_requested = False
        self._current_path: Optional[str] = None
        self._files_processed = 0
        self._last_run: Optional[datetime] = None
        self._next_run: Optional[datetime] = None
        self._lock = threading.Lock()

        # コンポーネントの初期化
        self._scanner = FileScanner(
            exclude_patterns=self.exclude_patterns,
            supported_extensions=self.supported_extensions,
            max_file_size_mb=self.max_file_size_mb
        )
        self._parser = DocumentParser(
            max_content_length=self.max_content_length
        )

    def start(self) -> None:
        """
        スケジューラーを開始する

        定期実行ジョブを登録し、バックグラウンドスケジューラーを開始します。
        """
        # 定期実行ジョブを登録
        self._scheduler.add_job(
            self._run_crawl_job,
            trigger=IntervalTrigger(minutes=self.interval_minutes),
            id='crawl_job',
            name='File Crawler',
            replace_existing=True
        )

        # スケジューラーを開始
        self._scheduler.start()
        logger.info(f"スケジューラーを開始しました（間隔: {self.interval_minutes}分）")

        # 次回実行時刻を更新
        job = self._scheduler.get_job('crawl_job')
        if job and job.next_run_time:
            self._next_run = job.next_run_time

        # 起動時に初回クロールを実行
        threading.Thread(target=self._run_crawl_job, daemon=True).start()

    def stop(self) -> None:
        """
        スケジューラーを停止する

        実行中のクロールがあれば停止を要求し、
        スケジューラーをシャットダウンします。
        """
        self._stop_requested = True
        self._scheduler.shutdown(wait=False)
        logger.info("スケジューラーを停止しました")

    def run_now(self) -> bool:
        """
        クロールを手動で即座に実行する

        既にクロールが実行中の場合は False を返します。

        Returns:
            bool: 実行を開始できた場合は True
        """
        with self._lock:
            if self._is_running:
                logger.warning("クロールは既に実行中です")
                return False

        # バックグラウンドスレッドで実行
        threading.Thread(target=self._run_crawl_job, daemon=True).start()
        return True

    def stop_current_crawl(self) -> None:
        """
        実行中のクロールを停止する

        現在実行中のクロール処理に停止を要求します。
        次回のスケジュールされた実行には影響しません。
        """
        self._stop_requested = True
        logger.info("クロール停止を要求しました")

    def get_status(self) -> Dict[str, Any]:
        """
        スケジューラーの現在の状態を取得する

        Returns:
            dict: 状態情報を含む辞書
                - is_running: クロール実行中かどうか
                - last_run: 最後にクロールを実行した日時
                - next_run: 次回クロール予定日時
                - files_processed: 処理済みファイル数
                - current_path: 現在処理中のパス
        """
        with self._lock:
            # 次回実行時刻を更新
            job = self._scheduler.get_job('crawl_job')
            if job and job.next_run_time:
                self._next_run = job.next_run_time

            return {
                "is_running": self._is_running,
                "last_run": self._last_run.isoformat() if self._last_run else None,
                "next_run": self._next_run.isoformat() if self._next_run else None,
                "files_processed": self._files_processed,
                "current_path": self._current_path
            }

    def _run_crawl_job(self) -> None:
        """
        クロールジョブを実行する（内部メソッド）

        この関数は定期実行またはrun_now()から呼び出されます。
        スキャン、パース、インデックス登録の一連の処理を実行します。
        """
        # 重複実行の防止
        with self._lock:
            if self._is_running:
                logger.warning("クロールは既に実行中のためスキップします")
                return
            self._is_running = True
            self._stop_requested = False
            self._files_processed = 0

        logger.info("=" * 60)
        logger.info("クロールを開始します")
        logger.info("=" * 60)

        start_time = datetime.now()

        try:
            # 新しいイベントループを作成して非同期処理を実行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                loop.run_until_complete(self._crawl_all_paths())
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"クロール中にエラーが発生しました: {e}", exc_info=True)

        finally:
            # 状態をリセット
            with self._lock:
                self._is_running = False
                self._current_path = None
                self._last_run = datetime.now()

            elapsed = datetime.now() - start_time
            logger.info("=" * 60)
            logger.info(f"クロール完了: {self._files_processed} ファイル処理")
            logger.info(f"所要時間: {elapsed}")
            logger.info("=" * 60)

    async def _crawl_all_paths(self) -> None:
        """
        全てのスキャンパスをクロールする（内部メソッド）

        設定されている全てのスキャンパスを順番に処理します。
        """
        for scan_path in self.scan_paths:
            if self._stop_requested:
                logger.info("クロールが停止されました")
                break

            with self._lock:
                self._current_path = scan_path

            logger.info(f"スキャン中: {scan_path}")

            try:
                await self._crawl_path(scan_path)
            except Exception as e:
                logger.error(f"パスのクロールに失敗: {scan_path} - {e}")

    async def _crawl_path(self, scan_path: str) -> None:
        """
        指定されたパスをクロールする（内部メソッド）

        1. ファイルをスキャン
        2. テキストを抽出
        3. インデックスに登録

        Args:
            scan_path: スキャンするディレクトリパス
        """
        documents = []

        # ファイルスキャン
        for file_info in self._scanner.scan(scan_path):
            if self._stop_requested:
                break

            # テキスト抽出
            content = None
            if file_info.size <= self.max_file_size_mb * 1024 * 1024:
                if self._parser.is_supported(file_info.path):
                    content = self._parser.extract_text(file_info.path)

            # ドキュメントを構築
            doc = self._build_document(file_info, content)
            documents.append(doc)

            self._files_processed += 1

            # バッチサイズに達したらインデックスに登録
            if len(documents) >= self.batch_size:
                await self._index_documents(documents)
                documents = []

                # CPU負荷を軽減するため少し待機
                await asyncio.sleep(0.1)

        # 残りのドキュメントを登録
        if documents:
            await self._index_documents(documents)

    def _build_document(self, file_info: FileInfo, content: Optional[str]) -> Dict[str, Any]:
        """
        Meilisearchに登録するドキュメントを構築する（内部メソッド）

        Args:
            file_info: ファイル情報
            content: 抽出されたテキスト（またはNone）

        Returns:
            dict: Meilisearchドキュメント
        """
        return {
            "id": file_info.id,
            "path": file_info.path,
            "filename": file_info.filename,
            "extension": file_info.extension,
            "size": file_info.size,
            "modified_at": file_info.modified_at,
            "created_at": file_info.created_at,
            "content": content or "",  # Noneの場合は空文字列
            "indexed_at": datetime.now().isoformat()
        }

    async def _index_documents(self, documents: List[Dict]) -> None:
        """
        ドキュメントをMeilisearchに登録する（内部メソッド）

        Args:
            documents: 登録するドキュメントのリスト
        """
        if not documents:
            return

        try:
            logger.info(f"インデックス登録開始: {len(documents)} 件")
            count = await self.meilisearch_client.add_documents(
                documents,
                batch_size=self.batch_size
            )
            logger.info(f"インデックス登録完了: {count} 件 / {len(documents)} 件が成功")
        except Exception as e:
            logger.error(f"ドキュメント登録エラー: {e}", exc_info=True)
