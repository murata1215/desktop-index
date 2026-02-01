# =============================================================================
# Desktop Index - Meilisearch クライアント
# =============================================================================
# Meilisearch との通信を行うクライアントクラスを提供します。
#
# 主な機能:
#   - インデックスの作成・設定
#   - ドキュメントの追加・更新・削除
#   - 全文検索
#   - 統計情報の取得
# =============================================================================

import logging
from typing import List, Dict, Optional, Any, Union
import meilisearch
from meilisearch.errors import MeilisearchApiError

logger = logging.getLogger(__name__)


def _get_task_uid(task_info: Any) -> Optional[int]:
    """
    タスク情報から task_uid を取得するヘルパー関数

    Meilisearch ライブラリのバージョンによって、タスク情報が
    辞書または TaskInfo オブジェクトで返されるため、両方に対応する。

    Args:
        task_info: タスク情報（dict または TaskInfo オブジェクト）

    Returns:
        int: タスクUID、取得できない場合は None
    """
    # TaskInfo オブジェクト（新しいバージョン）の場合
    if hasattr(task_info, 'task_uid'):
        return task_info.task_uid
    # 辞書（古いバージョン）の場合
    if isinstance(task_info, dict):
        return task_info.get("taskUid") or task_info.get("uid")
    return None


def _get_task_status(result: Any) -> str:
    """
    タスク結果からステータスを取得するヘルパー関数

    Args:
        result: タスク結果（dict または Task オブジェクト）

    Returns:
        str: タスクステータス
    """
    if hasattr(result, 'status'):
        return result.status
    if isinstance(result, dict):
        return result.get("status", "unknown")
    return "unknown"


def _get_task_error(result: Any) -> Any:
    """
    タスク結果からエラー情報を取得するヘルパー関数

    Args:
        result: タスク結果（dict または Task オブジェクト）

    Returns:
        エラー情報
    """
    if hasattr(result, 'error'):
        return result.error
    if isinstance(result, dict):
        return result.get("error", {})
    return None


class MeilisearchClient:
    """
    Meilisearch との通信を行うクライアントクラス

    このクラスは Meilisearch API のラッパーとして機能し、
    以下の操作を提供します:
    - インデックスの初期化と設定
    - ドキュメントのバッチ追加
    - 全文検索
    - ドキュメントの削除

    使用例:
        client = MeilisearchClient(
            host="http://localhost:7700",
            index_name="files"
        )
        await client.initialize_index()
        await client.add_documents([{...}, {...}])
        results = await client.search("検索キーワード")

    Attributes:
        host: Meilisearch サーバーの URL
        api_key: 認証用 API キー（オプション）
        index_name: 使用するインデックス名
    """

    def __init__(
        self,
        host: str = "http://localhost:7700",
        api_key: Optional[str] = None,
        index_name: str = "files"
    ):
        """
        MeilisearchClient を初期化する

        Args:
            host: Meilisearch サーバーの URL
            api_key: 認証用 API キー（本番環境では必須）
            index_name: 使用するインデックス名
        """
        self.host = host
        self.api_key = api_key
        self.index_name = index_name

        # Meilisearch クライアントの初期化
        self.client = meilisearch.Client(host, api_key)
        self.index = self.client.index(index_name)

    async def initialize_index(self) -> None:
        """
        インデックスを初期化する

        インデックスが存在しない場合は作成し、
        検索設定（検索可能属性、フィルター可能属性等）を適用します。

        この関数はアプリケーション起動時に一度だけ呼び出されます。
        """
        try:
            # インデックスの存在確認
            try:
                self.client.get_index(self.index_name)
                logger.info(f"既存のインデックスを使用: {self.index_name}")
            except MeilisearchApiError as e:
                if "index_not_found" in str(e):
                    # インデックスが存在しない場合は作成
                    logger.info(f"インデックスを作成: {self.index_name}")
                    task = self.client.create_index(
                        self.index_name,
                        {"primaryKey": "id"}
                    )
                    self._wait_for_task(task)
                else:
                    raise

            # 検索設定の適用
            await self._configure_index_settings()

        except Exception as e:
            logger.error(f"インデックス初期化エラー: {e}")
            raise

    async def _configure_index_settings(self) -> None:
        """
        インデックスの検索設定を適用する

        以下の設定を行います:
        - 検索可能属性（searchableAttributes）: 検索対象となるフィールド
        - フィルター可能属性（filterableAttributes）: フィルター検索で使用可能なフィールド
        - ソート可能属性（sortableAttributes）: ソートに使用可能なフィールド
        - ランキングルール: 検索結果の順序を決定するルール
        - ローカライズ属性（localizedAttributes）: 日本語トークナイザーの適用
        """
        # 検索可能な属性を設定
        # filename と content を検索対象にし、path も検索可能にする
        searchable_attributes = [
            "filename",
            "content",
            "path"
        ]

        # フィルター可能な属性を設定
        # 拡張子、更新日時、サイズでフィルタリングできるようにする
        filterable_attributes = [
            "extension",
            "modified_at",
            "size"
        ]

        # ソート可能な属性を設定
        sortable_attributes = [
            "modified_at",
            "size",
            "filename"
        ]

        # ランキングルールを設定
        # デフォルトのルールに加え、更新日時を考慮
        ranking_rules = [
            "words",          # 検索語の一致数
            "typo",           # タイポの少なさ
            "proximity",      # 検索語の近さ
            "attribute",      # 属性の優先順位
            "sort",           # ソート指定
            "exactness",      # 完全一致度
            "modified_at:desc"  # 新しいファイルを優先
        ]

        # ローカライズ属性を設定（日本語トークナイザー）
        # Meilisearch v1.10 以降で利用可能
        # これにより「田口」で検索すると「田口」を含むドキュメントのみがヒットする
        # （「田」や「口」だけでマッチしなくなる）
        localized_attributes = [
            {
                "locales": ["jpn"],  # 日本語トークナイザーを適用
                "attributePatterns": ["filename", "content", "path"]
            }
        ]

        try:
            # 各設定を適用（非同期で実行）
            tasks = []

            task = self.index.update_searchable_attributes(searchable_attributes)
            tasks.append(task)

            task = self.index.update_filterable_attributes(filterable_attributes)
            tasks.append(task)

            task = self.index.update_sortable_attributes(sortable_attributes)
            tasks.append(task)

            task = self.index.update_ranking_rules(ranking_rules)
            tasks.append(task)

            # 日本語トークナイザーの設定を適用
            # Meilisearch v1.10 以降で利用可能
            try:
                task = self.index.update_localized_attributes(localized_attributes)
                tasks.append(task)
                logger.info("日本語トークナイザー設定を追加しました")
            except AttributeError:
                # 古いバージョンの meilisearch-python では update_localized_attributes が存在しない
                logger.warning("日本語トークナイザー設定はサポートされていません（meilisearch-python をアップデートしてください）")
            except MeilisearchApiError as e:
                # Meilisearch サーバーが localizedAttributes をサポートしていない場合
                logger.warning(f"日本語トークナイザー設定に失敗: {e}")

            # 全てのタスクが完了するまで待機
            for task in tasks:
                self._wait_for_task(task)

            logger.info("インデックス設定を適用しました")

        except Exception as e:
            logger.warning(f"インデックス設定の適用に失敗: {e}")

    def _wait_for_task(self, task_info: Any, timeout_ms: int = 120000) -> Any:
        """
        Meilisearch タスクの完了を待機する

        Meilisearch の操作は非同期で実行されるため、
        タスクの完了を待機する必要があります。

        Args:
            task_info: タスク情報（TaskInfo オブジェクトまたは辞書）
            timeout_ms: タイムアウト時間（ミリ秒）、デフォルト2分

        Returns:
            完了したタスクの情報

        Raises:
            Exception: タスクが失敗した場合
        """
        task_uid = _get_task_uid(task_info)
        if task_uid is None:
            logger.warning(f"タスク情報にtaskUidがありません: {task_info}")
            return task_info

        try:
            logger.debug(f"タスク待機中: taskUid={task_uid}")
            result = self.client.wait_for_task(task_uid, timeout_ms)
            status = _get_task_status(result)

            if status == "failed":
                error_info = _get_task_error(result)
                logger.error(f"タスク失敗: taskUid={task_uid}, error={error_info}")
            elif status == "succeeded":
                logger.debug(f"タスク成功: taskUid={task_uid}")
            else:
                logger.warning(f"タスク状態: taskUid={task_uid}, status={status}")

            return result
        except Exception as e:
            logger.error(f"タスク待機エラー: taskUid={task_uid}, error={e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def add_documents(
        self,
        documents: List[Dict],
        batch_size: int = 1000
    ) -> int:
        """
        ドキュメントをインデックスに追加する

        大量のドキュメントを効率的に追加するため、
        バッチ処理を行います。

        Args:
            documents: 追加するドキュメントのリスト
                      各ドキュメントは id, path, filename, content 等を含む辞書
            batch_size: 1回のAPIコールで送信するドキュメント数

        Returns:
            int: 追加されたドキュメント数
        """
        if not documents:
            return 0

        total_added = 0

        # バッチに分割して処理
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            try:
                logger.info(f"Meilisearchにバッチ送信中: {len(batch)} 件...")
                task = self.index.add_documents(batch)
                task_uid = _get_task_uid(task)
                logger.info(f"タスク作成: taskUid={task_uid}")

                # タスク完了を待機
                result = self._wait_for_task(task)
                task_status = _get_task_status(result)

                if task_status == "succeeded":
                    total_added += len(batch)
                    logger.info(f"バッチ追加成功: {len(batch)} 件 (taskUid={task_uid})")
                else:
                    error_info = _get_task_error(result)
                    logger.error(f"バッチ追加失敗: status={task_status}, error={error_info}")

            except Exception as e:
                logger.error(f"ドキュメント追加エラー: {e}", exc_info=True)
                # エラーが発生しても続行（部分的な成功を許容）

        logger.info(f"ドキュメント追加完了: {total_added} 件 / {len(documents)} 件")
        return total_added

    async def delete_documents(self, document_ids: List[str]) -> int:
        """
        ドキュメントをインデックスから削除する

        Args:
            document_ids: 削除するドキュメントのIDリスト

        Returns:
            int: 削除されたドキュメント数
        """
        if not document_ids:
            return 0

        try:
            task = self.index.delete_documents(document_ids)
            self._wait_for_task(task)
            logger.info(f"ドキュメント削除完了: {len(document_ids)} 件")
            return len(document_ids)
        except Exception as e:
            logger.error(f"ドキュメント削除エラー: {e}")
            return 0

    async def search(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[str] = None,
        sort: Optional[List[str]] = None,
        attributes_to_highlight: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        インデックスを検索する

        全文検索を実行し、マッチしたドキュメントを返します。
        フィルター、ソート、ハイライト等のオプションが使用可能です。

        Args:
            query: 検索クエリ文字列
            limit: 返す結果の最大数（デフォルト: 20）
            offset: スキップする結果数（ページネーション用）
            filters: フィルター条件（例: "extension = '.pdf'"）
            sort: ソート条件のリスト（例: ["modified_at:desc"]）
            attributes_to_highlight: ハイライト対象の属性リスト

        Returns:
            dict: 検索結果を含む辞書
                - hits: マッチしたドキュメントのリスト
                - estimatedTotalHits: 推定総件数
                - processingTimeMs: 処理時間（ミリ秒）

        Example:
            results = await client.search(
                "議事録",
                filters="extension = '.docx'",
                sort=["modified_at:desc"],
                attributes_to_highlight=["filename", "content"]
            )
        """
        search_params = {
            "limit": limit,
            "offset": offset
        }

        if filters:
            search_params["filter"] = filters

        if sort:
            search_params["sort"] = sort

        if attributes_to_highlight:
            search_params["attributesToHighlight"] = attributes_to_highlight
            # ハイライトタグの設定
            search_params["highlightPreTag"] = "<mark>"
            search_params["highlightPostTag"] = "</mark>"
            # クロップ設定（長いテキストを適切な長さに切り詰め）
            search_params["attributesToCrop"] = ["content"]
            search_params["cropLength"] = 200

        try:
            results = self.index.search(query, search_params)
            return results
        except Exception as e:
            logger.error(f"検索エラー: {e}")
            return {
                "hits": [],
                "estimatedTotalHits": 0,
                "processingTimeMs": 0,
                "error": str(e)
            }

    async def get_stats(self) -> Dict[str, Any]:
        """
        インデックスの統計情報を取得する

        Returns:
            dict: 統計情報を含む辞書
                - numberOfDocuments: ドキュメント総数
                - isIndexing: インデックス処理中かどうか
                - fieldDistribution: フィールドごとのドキュメント数
        """
        try:
            stats = self.index.get_stats()
            logger.debug(f"統計情報取得: type={type(stats)}, value={stats}")

            # Meilisearch ライブラリのバージョンによって
            # 辞書または IndexStats オブジェクトで返されるため、両方に対応
            if hasattr(stats, 'number_of_documents'):
                # IndexStats オブジェクト（新しいバージョン）の場合
                # 属性名は snake_case で定義されている
                return {
                    "numberOfDocuments": stats.number_of_documents,
                    "isIndexing": getattr(stats, 'is_indexing', False),
                    "fieldDistribution": getattr(stats, 'field_distribution', {})
                }
            elif isinstance(stats, dict):
                # 辞書（古いバージョン）の場合
                return stats
            else:
                # その他の場合は属性からアクセスを試みる（camelCase）
                return {
                    "numberOfDocuments": getattr(stats, 'numberOfDocuments', 0),
                    "isIndexing": getattr(stats, 'isIndexing', False),
                    "fieldDistribution": getattr(stats, 'fieldDistribution', {})
                }
        except Exception as e:
            logger.error(f"統計情報取得エラー: {e}", exc_info=True)
            return {
                "numberOfDocuments": 0,
                "isIndexing": False,
                "error": str(e)
            }

    async def clear_index(self) -> bool:
        """
        インデックス内の全ドキュメントを削除する

        注意: この操作は元に戻せません。

        Returns:
            bool: 成功した場合は True
        """
        try:
            task = self.index.delete_all_documents()
            self._wait_for_task(task)
            logger.info("インデックスをクリアしました")
            return True
        except Exception as e:
            logger.error(f"インデックスクリアエラー: {e}")
            return False

    async def health_check(self) -> bool:
        """
        Meilisearch サーバーの健全性をチェックする

        Returns:
            bool: サーバーが正常に動作している場合は True
        """
        try:
            health = self.client.health()
            return health.get("status") == "available"
        except Exception as e:
            logger.error(f"ヘルスチェック失敗: {e}")
            return False
