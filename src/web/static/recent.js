/**
 * =============================================================================
 * Desktop Index - 最近のファイル機能
 * =============================================================================
 *
 * 最近更新されたファイル（Office系）を取得・表示するモジュール。
 *
 * 機能:
 * - 1週間以内に更新されたファイルを取得
 * - 拡張子でフィルタリング（All, PDF, Word, Excel）
 * - クリックでファイルの親フォルダをエクスプローラーで開く
 *
 * =============================================================================
 */

// ---------------------------------------------------------------------------
// 定数定義
// ---------------------------------------------------------------------------

/**
 * APIエンドポイント
 */
const API_RECENT = '/api/recent';
const API_OPEN_FOLDER = '/api/open-folder';

/**
 * フィルター定義
 * data-filter 属性値と API パラメータのマッピング
 */
const FILTER_MAP = {
    all: null,              // すべて（フィルターなし）
    pdf: 'pdf',             // PDFのみ
    word: 'docx',           // Wordのみ（.doc, .docxをdocxで代表）
    excel: 'xlsx'           // Excelのみ（.xls, .xlsxをxlsxで代表）
};

/**
 * ファイルアイコンマッピング
 * 拡張子に対応する絵文字アイコン
 */
const FILE_ICONS = {
    '.pdf': '📕',
    '.doc': '📘',
    '.docx': '📘',
    '.xls': '📗',
    '.xlsx': '📗',
    '.ppt': '📙',
    '.pptx': '📙',
    default: '📄'
};

// ---------------------------------------------------------------------------
// グローバル状態
// ---------------------------------------------------------------------------

/**
 * 現在選択中のフィルター
 */
let currentFilter = 'all';

/**
 * 取得済みの全ファイルデータ（フィルタリング用にキャッシュ）
 */
let allFilesCache = [];

// ---------------------------------------------------------------------------
// 初期化
// ---------------------------------------------------------------------------

/**
 * DOMContentLoaded時に最近のファイル機能を初期化
 *
 * 処理内容:
 * 1. フィルターボタンにイベントリスナーを設定
 * 2. 最近のファイルを取得・表示
 */
document.addEventListener('DOMContentLoaded', () => {
    initFilterButtons();
    loadRecentFiles();
});

/**
 * フィルターボタンの初期化
 *
 * 各ボタンにクリックイベントを設定し、
 * フィルター切り替え時に一覧を再描画する。
 */
function initFilterButtons() {
    const buttons = document.querySelectorAll('.recent-filter-btn');

    buttons.forEach(button => {
        button.addEventListener('click', () => {
            // アクティブ状態を切り替え
            buttons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            // フィルター値を取得して適用
            currentFilter = button.getAttribute('data-filter') || 'all';

            // キャッシュからフィルタリングして表示
            displayFilteredFiles();
        });
    });
}

// ---------------------------------------------------------------------------
// データ取得
// ---------------------------------------------------------------------------

/**
 * 最近のファイルをAPIから取得
 *
 * @param {number} days - 取得する期間（日数）、デフォルト7日
 *
 * 処理内容:
 * 1. APIにリクエストを送信
 * 2. レスポンスをキャッシュに保存
 * 3. フィルタリングして表示
 */
async function loadRecentFiles(days = 7) {
    const container = document.getElementById('recentFilesList');
    if (!container) return;

    // ローディング表示
    container.innerHTML = `
        <div class="recent-files-loading">
            <span class="loading-spinner"></span>
            読み込み中...
        </div>
    `;

    try {
        // APIリクエスト（フィルターなしで全件取得）
        const response = await fetch(`${API_RECENT}?days=${days}`);

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        const data = await response.json();

        // キャッシュに保存
        allFilesCache = data.hits || [];

        // フィルタリングして表示
        displayFilteredFiles();

    } catch (error) {
        console.error('最近のファイル取得エラー:', error);
        container.innerHTML = `
            <div class="recent-files-error">
                ⚠️ ファイルの取得に失敗しました<br>
                <small>${error.message}</small>
            </div>
        `;
    }
}

// ---------------------------------------------------------------------------
// 表示処理
// ---------------------------------------------------------------------------

/**
 * キャッシュからフィルタリングして表示
 *
 * currentFilter の値に基づいてファイルをフィルタリングし、
 * DOM に描画する。
 */
function displayFilteredFiles() {
    const container = document.getElementById('recentFilesList');
    if (!container) return;

    // フィルタリング
    let filteredFiles = allFilesCache;

    if (currentFilter !== 'all') {
        const filterExt = FILTER_MAP[currentFilter];
        if (filterExt) {
            filteredFiles = allFilesCache.filter(file => {
                const ext = (file.extension || '').toLowerCase();
                // Word: .doc, .docx
                if (currentFilter === 'word') {
                    return ext === '.doc' || ext === '.docx';
                }
                // Excel: .xls, .xlsx
                if (currentFilter === 'excel') {
                    return ext === '.xls' || ext === '.xlsx';
                }
                // その他: 完全一致
                return ext === `.${filterExt}`;
            });
        }
    }

    // 結果なしの場合
    if (filteredFiles.length === 0) {
        container.innerHTML = `
            <div class="recent-files-empty">
                📭 該当するファイルがありません
            </div>
        `;
        return;
    }

    // ファイル一覧を描画
    const html = filteredFiles.map(file => createFileItemHTML(file)).join('');
    container.innerHTML = html + `
        <div class="recent-files-count">
            ${filteredFiles.length} 件のファイル
        </div>
    `;

    // クリックイベントを設定
    attachClickHandlers();
}

/**
 * ファイルアイテムのHTMLを生成
 *
 * @param {Object} file - ファイル情報オブジェクト
 * @returns {string} HTMLコード
 */
function createFileItemHTML(file) {
    const icon = getFileIcon(file.extension);
    const date = formatRelativeDate(file.modified_at);
    const folderPath = getFolderPath(file.path);

    // ファイル名が長い場合は省略
    const filename = file.filename.length > 30
        ? file.filename.substring(0, 27) + '...'
        : file.filename;

    return `
        <div class="recent-file-item" data-path="${escapeHTML(file.path)}" title="${escapeHTML(file.filename)}">
            <div class="recent-file-header">
                <span class="recent-file-icon">${icon}</span>
                <span class="recent-file-name">${escapeHTML(filename)}</span>
            </div>
            <div class="recent-file-path" title="${escapeHTML(folderPath)}">${escapeHTML(folderPath)}</div>
            <div class="recent-file-date">📅 ${date}</div>
        </div>
    `;
}

/**
 * クリックイベントハンドラーを設定
 *
 * 各ファイルアイテムにクリックイベントを設定し、
 * クリック時にフォルダを開くAPIを呼び出す。
 */
function attachClickHandlers() {
    const items = document.querySelectorAll('.recent-file-item');

    items.forEach(item => {
        item.addEventListener('click', async () => {
            const path = item.getAttribute('data-path');
            if (!path) return;

            // ビジュアルフィードバック
            item.style.opacity = '0.6';

            try {
                await openFolder(path);
            } catch (error) {
                console.error('フォルダを開くエラー:', error);
                alert(`フォルダを開けませんでした: ${error.message}`);
            } finally {
                item.style.opacity = '1';
            }
        });
    });
}

// ---------------------------------------------------------------------------
// フォルダを開く
// ---------------------------------------------------------------------------

/**
 * ファイルの親フォルダをエクスプローラーで開く
 *
 * @param {string} path - ファイルのフルパス
 * @returns {Promise<void>}
 *
 * Windows の explorer /select,"path" コマンドが実行され、
 * ファイルが選択された状態でフォルダが開く。
 */
async function openFolder(path) {
    const response = await fetch(API_OPEN_FOLDER, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ path })
    });

    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Unknown error');
    }

    return response.json();
}

// ---------------------------------------------------------------------------
// ユーティリティ関数
// ---------------------------------------------------------------------------

/**
 * ファイル拡張子に対応するアイコンを取得
 *
 * @param {string} extension - 拡張子（例: ".pdf"）
 * @returns {string} 絵文字アイコン
 */
function getFileIcon(extension) {
    const ext = (extension || '').toLowerCase();
    return FILE_ICONS[ext] || FILE_ICONS.default;
}

/**
 * ファイルパスから親フォルダパスを取得
 *
 * @param {string} path - ファイルのフルパス
 * @returns {string} 親フォルダパス
 */
function getFolderPath(path) {
    if (!path) return '';
    // Windows パス区切り文字で分割して最後の要素（ファイル名）を除去
    const parts = path.replace(/\//g, '\\').split('\\');
    parts.pop();
    return parts.join('\\');
}

/**
 * 日時を相対表示にフォーマット
 *
 * @param {string} dateString - ISO 8601 形式の日時文字列
 * @returns {string} 相対表示（例: "3時間前", "2日前"）
 */
function formatRelativeDate(dateString) {
    if (!dateString) return '';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMinutes < 1) return '今';
    if (diffMinutes < 60) return `${diffMinutes}分前`;
    if (diffHours < 24) return `${diffHours}時間前`;
    if (diffDays < 7) return `${diffDays}日前`;

    // 7日以上前は日付表示
    return date.toLocaleDateString('ja-JP', {
        month: 'short',
        day: 'numeric'
    });
}

/**
 * HTML特殊文字をエスケープ
 *
 * @param {string} str - エスケープする文字列
 * @returns {string} エスケープ済み文字列
 */
function escapeHTML(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
