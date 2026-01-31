# =============================================================================
# Desktop Index - インデクサーパッケージ
# =============================================================================
# Meilisearch との連携を行うモジュール群
#
# モジュール構成:
#   - meilisearch_client.py: Meilisearch API クライアント
# =============================================================================

from src.indexer.meilisearch_client import MeilisearchClient

__all__ = ["MeilisearchClient"]
