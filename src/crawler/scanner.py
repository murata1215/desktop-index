# =============================================================================
# Desktop Index - ファイルスキャナー
# =============================================================================
# 指定されたディレクトリを再帰的に巡回し、ファイルのメタデータを収集します。
#
# 主な機能:
#   - ディレクトリの再帰的巡回
#   - 除外パターンによるフィルタリング
#   - ファイルメタデータの収集（パス、サイズ、更新日時等）
#   - 差分検出（前回スキャンとの比較）
# =============================================================================

import os
import hashlib
import fnmatch
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Generator, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ファイル情報データクラス
# ---------------------------------------------------------------------------
@dataclass
class FileInfo:
    """
    スキャンされたファイルの情報を保持するデータクラス

    Attributes:
        path: ファイルのフルパス
        filename: ファイル名（拡張子含む）
        extension: ファイルの拡張子（小文字、ドット付き）
        size: ファイルサイズ（バイト）
        modified_at: 最終更新日時（ISO 8601形式の文字列）
        created_at: 作成日時（ISO 8601形式の文字列）
        id: ドキュメントID（パスのハッシュ値）
    """
    path: str
    filename: str
    extension: str
    size: int
    modified_at: str
    created_at: str
    id: str = field(default="")

    def __post_init__(self):
        """
        初期化後処理: IDが未設定の場合、パスからハッシュ値を生成する

        IDはMeilisearchのドキュメント識別子として使用される。
        パスをSHA256でハッシュ化することで、一意かつ安定したIDを生成する。
        """
        if not self.id:
            # パスをUTF-8でエンコードしてSHA256ハッシュを生成
            # 先頭16文字を使用（十分な一意性を確保）
            self.id = hashlib.sha256(self.path.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# ファイルスキャナークラス
# ---------------------------------------------------------------------------
class FileScanner:
    """
    ファイルシステムを巡回してファイル情報を収集するクラス

    このクラスは以下の機能を提供します:
    - 指定ディレクトリの再帰的スキャン
    - 除外パターンによるファイル/フォルダのフィルタリング
    - 対象拡張子によるフィルタリング
    - ジェネレータによるメモリ効率の良いスキャン

    使用例:
        scanner = FileScanner(
            exclude_patterns=["*.tmp", "node_modules"],
            supported_extensions=[".pdf", ".docx", ".txt"]
        )
        for file_info in scanner.scan("/path/to/directory"):
            print(file_info.filename)
    """

    def __init__(
        self,
        exclude_patterns: List[str] = None,
        supported_extensions: List[str] = None,
        max_file_size_mb: int = 50
    ):
        """
        FileScanner を初期化する

        Args:
            exclude_patterns: 除外するファイル/フォルダのパターンリスト
                             ワイルドカード（*、?）が使用可能
            supported_extensions: インデックス対象の拡張子リスト
                                 ドット付きの小文字で指定（例: [".pdf", ".txt"]）
            max_file_size_mb: 処理対象の最大ファイルサイズ（MB）
        """
        self.exclude_patterns = exclude_patterns or []
        self.supported_extensions = set(
            ext.lower() for ext in (supported_extensions or [])
        )
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        # スキャン統計情報
        self._stats = {
            "total_files": 0,
            "skipped_by_pattern": 0,
            "skipped_by_extension": 0,
            "skipped_by_size": 0,
            "skipped_by_error": 0
        }

    def scan(self, root_path: str) -> Generator[FileInfo, None, None]:
        """
        指定されたディレクトリを再帰的にスキャンする

        この関数はジェネレータとして実装されており、
        ファイルを見つけるたびに FileInfo オブジェクトを yield します。
        これにより、大量のファイルを処理する際もメモリ使用量を抑えられます。

        Args:
            root_path: スキャン開始ディレクトリのパス

        Yields:
            FileInfo: 見つかったファイルの情報

        Note:
            - シンボリックリンクは追跡しません（無限ループ防止）
            - アクセス権限のないディレクトリはスキップされます
            - 除外パターンに一致するファイル/フォルダはスキップされます
        """
        root = Path(root_path)

        # ルートパスの存在確認
        if not root.exists():
            logger.warning(f"スキャンパスが存在しません: {root_path}")
            return

        if not root.is_dir():
            logger.warning(f"スキャンパスがディレクトリではありません: {root_path}")
            return

        logger.info(f"スキャン開始: {root_path}")
        self._reset_stats()

        # os.walk を使用してディレクトリを再帰的に巡回
        # followlinks=False でシンボリックリンクを追跡しない
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # 除外パターンに一致するディレクトリをリストから削除
            # （os.walk はこのリストを参照して再帰を制御する）
            dirnames[:] = [
                d for d in dirnames
                if not self._should_exclude(d, is_dir=True)
            ]

            # 各ファイルを処理
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)

                # 除外パターンチェック
                if self._should_exclude(filename, is_dir=False):
                    self._stats["skipped_by_pattern"] += 1
                    continue

                # 拡張子チェック
                ext = Path(filename).suffix.lower()
                if self.supported_extensions and ext not in self.supported_extensions:
                    self._stats["skipped_by_extension"] += 1
                    continue

                # ファイル情報を取得して yield
                try:
                    file_info = self._get_file_info(file_path)
                    if file_info:
                        # サイズチェック
                        if file_info.size > self.max_file_size_bytes:
                            self._stats["skipped_by_size"] += 1
                            # サイズが大きいファイルもインデックス対象にはするが、
                            # 後続の処理でコンテンツ抽出をスキップするため、
                            # ここでは yield する
                        self._stats["total_files"] += 1
                        yield file_info
                except Exception as e:
                    logger.debug(f"ファイル情報取得エラー: {file_path} - {e}")
                    self._stats["skipped_by_error"] += 1

        logger.info(f"スキャン完了: {root_path}")
        logger.info(f"統計: {self._stats}")

    def _should_exclude(self, name: str, is_dir: bool = False) -> bool:
        """
        ファイル/フォルダが除外パターンに一致するかチェックする

        Args:
            name: チェック対象のファイル名またはフォルダ名
            is_dir: ディレクトリの場合は True

        Returns:
            bool: 除外すべき場合は True
        """
        for pattern in self.exclude_patterns:
            # fnmatch はワイルドカードパターンマッチングを行う
            # 例: "*.tmp" は "file.tmp" にマッチ
            # 例: "node_modules" は "node_modules" にマッチ
            if fnmatch.fnmatch(name, pattern):
                return True
            # フルパスパターン（例: "*/cache/*"）もサポート
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                return True
        return False

    def _get_file_info(self, file_path: str) -> Optional[FileInfo]:
        """
        ファイルのメタデータを取得して FileInfo オブジェクトを生成する

        Args:
            file_path: ファイルのフルパス

        Returns:
            FileInfo: ファイル情報、取得に失敗した場合は None

        Note:
            - ファイルが存在しない場合や読み取り権限がない場合は None を返す
            - 日時は ISO 8601 形式の文字列に変換される
        """
        try:
            stat = os.stat(file_path)
            path_obj = Path(file_path)

            return FileInfo(
                path=file_path,
                filename=path_obj.name,
                extension=path_obj.suffix.lower(),
                size=stat.st_size,
                # タイムスタンプを ISO 8601 形式に変換
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat()
            )
        except (OSError, PermissionError) as e:
            # アクセス権限がない、ファイルが存在しない等
            logger.debug(f"ファイル情報取得失敗: {file_path} - {e}")
            return None

    def _reset_stats(self):
        """スキャン統計情報をリセットする"""
        self._stats = {
            "total_files": 0,
            "skipped_by_pattern": 0,
            "skipped_by_extension": 0,
            "skipped_by_size": 0,
            "skipped_by_error": 0
        }

    def get_stats(self) -> Dict:
        """
        現在のスキャン統計情報を取得する

        Returns:
            dict: 統計情報を含む辞書
        """
        return self._stats.copy()


# ---------------------------------------------------------------------------
# 差分検出ユーティリティ
# ---------------------------------------------------------------------------
class DiffDetector:
    """
    前回のスキャン結果と比較して差分を検出するクラス

    このクラスは以下の差分を検出します:
    - 新規追加されたファイル
    - 更新されたファイル（更新日時が変更）
    - 削除されたファイル

    使用例:
        detector = DiffDetector()
        detector.load_previous_state(previous_files)  # 前回の状態を読み込み
        new, updated, deleted = detector.detect_changes(current_files)
    """

    def __init__(self):
        """DiffDetector を初期化する"""
        # 前回のスキャン結果を保持する辞書
        # キー: ファイルパス、値: 更新日時
        self._previous_state: Dict[str, str] = {}

    def load_previous_state(self, files: List[Dict]) -> None:
        """
        前回のスキャン結果を読み込む

        Args:
            files: 前回スキャンされたファイル情報のリスト
                   各要素は {"path": "...", "modified_at": "..."} の形式
        """
        self._previous_state = {
            f["path"]: f["modified_at"]
            for f in files
        }

    def detect_changes(
        self,
        current_files: List[FileInfo]
    ) -> tuple[List[FileInfo], List[FileInfo], Set[str]]:
        """
        現在のファイルリストと前回の状態を比較して差分を検出する

        Args:
            current_files: 現在スキャンされたファイル情報のリスト

        Returns:
            tuple: (新規ファイル, 更新ファイル, 削除されたファイルパスのセット)
        """
        new_files = []
        updated_files = []
        current_paths = set()

        for file_info in current_files:
            current_paths.add(file_info.path)

            if file_info.path not in self._previous_state:
                # 前回の状態に存在しない = 新規ファイル
                new_files.append(file_info)
            elif file_info.modified_at != self._previous_state[file_info.path]:
                # 更新日時が異なる = 更新されたファイル
                updated_files.append(file_info)

        # 前回存在したが今回存在しない = 削除されたファイル
        deleted_paths = set(self._previous_state.keys()) - current_paths

        return new_files, updated_files, deleted_paths

    def update_state(self, files: List[FileInfo]) -> None:
        """
        現在の状態で内部状態を更新する

        次回の差分検出のために、現在のファイルリストを保存します。

        Args:
            files: 現在のファイル情報リスト
        """
        self._previous_state = {
            f.path: f.modified_at
            for f in files
        }
