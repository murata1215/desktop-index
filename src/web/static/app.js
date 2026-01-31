/**
 * =============================================================================
 * Desktop Index - フロントエンド JavaScript
 * =============================================================================
 * クライアントサイドの共通機能を提供します。
 *
 * 主な機能:
 *   - クリップボードコピー
 *   - ファイルアイコン取得
 *   - ファイルサイズフォーマット
 *   - キーボードショートカット
 * =============================================================================
 */

/**
 * ページ読み込み時の初期化処理
 */
document.addEventListener('DOMContentLoaded', () => {
    // 検索フォームにフォーカス
    const searchInput = document.querySelector('.search-input-large, .search-input-compact');
    if (searchInput) {
        searchInput.focus();
    }

    // キーボードショートカットの設定
    setupKeyboardShortcuts();
});

/**
 * キーボードショートカットを設定する
 *
 * ショートカット:
 *   - / : 検索ボックスにフォーカス
 *   - Escape : 検索ボックスのフォーカスを外す
 */
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // 入力中は無視
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            // Escapeキーの場合はフォーカスを外す
            if (e.key === 'Escape') {
                e.target.blur();
            }
            return;
        }

        // "/" キーで検索ボックスにフォーカス
        if (e.key === '/') {
            e.preventDefault();
            const searchInput = document.querySelector('.search-input-large, .search-input-compact');
            if (searchInput) {
                searchInput.focus();
            }
        }
    });
}

/**
 * テキストをクリップボードにコピーする
 *
 * @param {string} text - コピーするテキスト
 * @returns {Promise<boolean>} コピー成功時は true
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('クリップボードにコピーしました');
        return true;
    } catch (err) {
        console.error('コピーに失敗しました:', err);
        showToast('コピーに失敗しました', 'error');
        return false;
    }
}

/**
 * トースト通知を表示する
 *
 * @param {string} message - 表示するメッセージ
 * @param {string} type - 通知タイプ（'success' | 'error'）
 */
function showToast(message, type = 'success') {
    // 既存のトーストを削除
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    // トースト要素を作成
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    // スタイルを適用
    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '20px',
        left: '50%',
        transform: 'translateX(-50%)',
        padding: '12px 24px',
        backgroundColor: type === 'error' ? '#ea4335' : '#34a853',
        color: 'white',
        borderRadius: '8px',
        fontSize: '14px',
        zIndex: '9999',
        animation: 'fadeIn 0.3s ease'
    });

    // ページに追加
    document.body.appendChild(toast);

    // 3秒後に削除
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * ファイル拡張子に対応するアイコンを取得する
 *
 * @param {string} extension - ファイル拡張子（例: '.pdf'）
 * @returns {string} 絵文字アイコン
 */
function getFileIcon(extension) {
    const iconMap = {
        // ドキュメント
        '.pdf': '📕',
        '.doc': '📘',
        '.docx': '📘',
        '.xls': '📗',
        '.xlsx': '📗',
        '.ppt': '📙',
        '.pptx': '📙',

        // テキスト
        '.txt': '📄',
        '.md': '📝',
        '.csv': '📊',
        '.json': '📋',
        '.xml': '📋',
        '.yaml': '📋',
        '.yml': '📋',

        // ソースコード
        '.py': '🐍',
        '.js': '📜',
        '.ts': '📜',
        '.html': '🌐',
        '.css': '🎨',
        '.java': '☕',
        '.c': '⚙️',
        '.cpp': '⚙️',
        '.go': '🔷',
        '.rs': '🦀',
        '.rb': '💎',
        '.php': '🐘',
        '.sql': '🗃️',

        // その他
        '.zip': '📦',
        '.rar': '📦',
        '.7z': '📦',
        '.tar': '📦',
        '.gz': '📦',

        '.jpg': '🖼️',
        '.jpeg': '🖼️',
        '.png': '🖼️',
        '.gif': '🖼️',
        '.svg': '🖼️',
        '.webp': '🖼️',

        '.mp3': '🎵',
        '.wav': '🎵',
        '.flac': '🎵',
        '.aac': '🎵',

        '.mp4': '🎬',
        '.avi': '🎬',
        '.mkv': '🎬',
        '.mov': '🎬',
        '.webm': '🎬',
    };

    return iconMap[extension.toLowerCase()] || '📄';
}

/**
 * ファイルサイズを人間が読みやすい形式にフォーマットする
 *
 * @param {number} bytes - ファイルサイズ（バイト）
 * @returns {string} フォーマットされたサイズ（例: '1.5 MB'）
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    if (!bytes) return '不明';

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + units[i];
}

/**
 * 日付を相対的な表現にフォーマットする
 *
 * @param {string} dateString - ISO 8601形式の日付文字列
 * @returns {string} 相対的な日付表現（例: '3日前'）
 */
function formatRelativeDate(dateString) {
    if (!dateString) return '不明';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return '今日';
    if (diffDays === 1) return '昨日';
    if (diffDays < 7) return `${diffDays}日前`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}週間前`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}ヶ月前`;
    return `${Math.floor(diffDays / 365)}年前`;
}

// CSS アニメーションを動的に追加
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateX(-50%) translateY(20px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
    @keyframes fadeOut {
        from { opacity: 1; transform: translateX(-50%) translateY(0); }
        to { opacity: 0; transform: translateX(-50%) translateY(20px); }
    }
`;
document.head.appendChild(style);
