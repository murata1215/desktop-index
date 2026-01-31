# =============================================================================
# Desktop Index - 設定管理モジュール
# =============================================================================
# config.yaml と環境変数から設定を読み込み、アプリケーション全体で
# 使用可能な設定オブジェクトを提供します。
#
# 使用方法:
#   from src.config import settings
#   print(settings.scan_paths)
# =============================================================================

import os
from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Meilisearch設定のデータクラス
# ---------------------------------------------------------------------------
class MeilisearchConfig(BaseModel):
    """
    Meilisearch接続設定を保持するクラス

    Attributes:
        host: MeilisearchサーバーのURL
        index_name: 使用するインデックス名
        api_key: 認証用APIキー（オプション）
    """
    host: str = "http://meilisearch:7700"
    index_name: str = "files"
    api_key: Optional[str] = None


# ---------------------------------------------------------------------------
# ログ設定のデータクラス
# ---------------------------------------------------------------------------
class LoggingConfig(BaseModel):
    """
    ログ出力設定を保持するクラス

    Attributes:
        level: ログレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        format: ログフォーマット文字列
    """
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# ---------------------------------------------------------------------------
# メイン設定クラス
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """
    アプリケーション全体の設定を管理するクラス

    設定の優先順位:
    1. 環境変数（最優先）
    2. config.yaml
    3. デフォルト値

    Attributes:
        scan_paths: スキャン対象のディレクトリパスリスト
        exclude_patterns: 除外するファイル/フォルダのパターン
        supported_extensions: インデックス対象の拡張子リスト
        scan_interval_minutes: 定期スキャンの間隔（分）
        batch_size: Meilisearchへのバッチ登録サイズ
        max_file_size_mb: 内容抽出対象の最大ファイルサイズ（MB）
        max_content_length: 抽出テキストの最大長（文字数）
        meilisearch: Meilisearch接続設定
        logging: ログ設定
    """

    # スキャン設定
    scan_paths: List[str] = Field(default_factory=lambda: ["/mnt/c_users"])
    exclude_patterns: List[str] = Field(default_factory=lambda: [
        "*.tmp", "node_modules", ".git", "__pycache__"
    ])
    supported_extensions: List[str] = Field(default_factory=lambda: [
        ".pdf", ".docx", ".xlsx", ".txt", ".md"
    ])

    # スケジュール設定
    scan_interval_minutes: int = 60

    # パフォーマンス設定
    batch_size: int = 1000
    max_file_size_mb: int = 50
    max_content_length: int = 100000

    # サブ設定
    meilisearch: MeilisearchConfig = Field(default_factory=MeilisearchConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    class Config:
        """Pydantic設定"""
        env_prefix = "DESKTOPINDEX_"  # 環境変数のプレフィックス


def load_config(config_path: str = "config.yaml") -> Settings:
    """
    設定ファイルを読み込み、Settingsオブジェクトを生成する

    この関数は以下の処理を行います:
    1. config.yaml ファイルを読み込む
    2. 環境変数で上書き可能な設定を適用する
    3. Meilisearchのホスト設定を環境変数から上書きする

    Args:
        config_path: 設定ファイルのパス（デフォルト: config.yaml）

    Returns:
        Settings: 読み込まれた設定オブジェクト

    Raises:
        FileNotFoundError: 設定ファイルが見つからない場合
        yaml.YAMLError: YAMLの解析に失敗した場合
    """
    # 設定ファイルのパスを解決
    config_file = Path(config_path)
    if not config_file.exists():
        # デフォルト設定で動作
        print(f"警告: 設定ファイル {config_path} が見つかりません。デフォルト設定を使用します。")
        return Settings()

    # YAMLファイルを読み込む
    with open(config_file, 'r', encoding='utf-8') as f:
        yaml_config = yaml.safe_load(f)

    # Meilisearch設定を構築
    meili_config = yaml_config.get('meilisearch', {})
    meilisearch = MeilisearchConfig(
        # 環境変数 MEILISEARCH_HOST が優先される
        host=os.environ.get('MEILISEARCH_HOST', meili_config.get('host', 'http://meilisearch:7700')),
        index_name=meili_config.get('index_name', 'files'),
        api_key=os.environ.get('MEILI_MASTER_KEY', meili_config.get('api_key'))
    )

    # ログ設定を構築
    log_config = yaml_config.get('logging', {})
    logging_settings = LoggingConfig(
        level=log_config.get('level', 'INFO'),
        format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )

    # メイン設定を構築
    settings = Settings(
        scan_paths=yaml_config.get('scan_paths', ['/mnt/c_users']),
        exclude_patterns=yaml_config.get('exclude_patterns', []),
        supported_extensions=yaml_config.get('supported_extensions', []),
        scan_interval_minutes=yaml_config.get('scan_interval_minutes', 60),
        batch_size=yaml_config.get('batch_size', 1000),
        max_file_size_mb=yaml_config.get('max_file_size_mb', 50),
        max_content_length=yaml_config.get('max_content_length', 100000),
        meilisearch=meilisearch,
        logging=logging_settings
    )

    return settings


# ---------------------------------------------------------------------------
# グローバル設定インスタンス
# ---------------------------------------------------------------------------
# アプリケーション起動時に一度だけ読み込まれる
# 他のモジュールからは `from src.config import settings` でアクセス可能
# ---------------------------------------------------------------------------
settings = load_config()
