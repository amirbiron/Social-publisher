/* ═══════════════════════════════════════════════════════════════
   Social Publisher — Frontend Application
   ═══════════════════════════════════════════════════════════════ */

// ─── State ─────────────────────────────────────────────────────
let posts = [];
let header = [];
let config = {};
let currentView = 'posts';
let calendarDate = new Date();
let deleteRowNumber = null;
let deletePostId = null;
let editPostId = null;

// Drive browser state
let driveStack = [];       // [{folderId, name}] for breadcrumb
let selectedDriveFile = null;

// Filter state
let filters = { status: '', network: '', dateFrom: '', dateTo: '', search: '' };

// Character limits
const CHAR_LIMITS = { ig: 2200, fb: 63206 };

// ─── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadConfig();
  await loadPosts();
});

async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    config = await resp.json();
  } catch (e) {
    console.error('Failed to load config:', e);
  }
}

// ═══════════════════════════════════════════════════════════════
//  Posts — CRUD
// ═══════════════════════════════════════════════════════════════

async function loadPosts() {
  showElement('posts-loading');
  hideElement('posts-empty');
  hideElement('posts-table-wrapper');

  try {
    const resp = await fetch('/api/posts');
    const data = await resp.json();

    if (data.error) {
      showToast(data.error, 'error');
      return;
    }

    posts = data.posts || [];
    header = data.header || [];
    renderPosts();
    updateStats();
    renderCalendar();
  } catch (e) {
    showToast('שגיאה בטעינת הפוסטים', 'error');
    console.error(e);
  } finally {
    hideElement('posts-loading');
  }
}

function getFilteredPosts() {
  return posts.filter(post => {
    const status = (post.status || '').toUpperCase();
    if (filters.status && status !== filters.status) return false;
    if (filters.network && (post.network || '') !== filters.network) return false;

    if (filters.dateFrom || filters.dateTo) {
      const pDate = parseDate(post.publish_at);
      if (!pDate) return false;
      if (filters.dateFrom) {
        const from = new Date(filters.dateFrom + 'T00:00:00');
        if (pDate < from) return false;
      }
      if (filters.dateTo) {
        const to = new Date(filters.dateTo + 'T23:59:59');
        if (pDate > to) return false;
      }
    }

    if (filters.search) {
      const q = filters.search.toLowerCase();
      const inIg = (post.caption_ig || '').toLowerCase().includes(q);
      const inFb = (post.caption_fb || '').toLowerCase().includes(q);
      if (!inIg && !inFb) return false;
    }

    return true;
  });
}

function applyFilters() {
  filters.status = document.getElementById('filter-status').value;
  filters.network = document.getElementById('filter-network').value;
  filters.dateFrom = document.getElementById('filter-date-from').value;
  filters.dateTo = document.getElementById('filter-date-to').value;
  filters.search = document.getElementById('filter-search').value;
  renderPosts();
}

function clearFilters() {
  document.getElementById('filter-status').value = '';
  document.getElementById('filter-network').value = '';
  document.getElementById('filter-date-from').value = '';
  document.getElementById('filter-date-to').value = '';
  document.getElementById('filter-search').value = '';
  filters = { status: '', network: '', dateFrom: '', dateTo: '', search: '' };
  renderPosts();
}

function renderPosts() {
  const tbody = document.getElementById('posts-tbody');
  const cardsEl = document.getElementById('posts-cards');
  const filtered = getFilteredPosts();

  if (filtered.length === 0) {
    if (posts.length === 0) {
      showElement('posts-empty');
    } else {
      hideElement('posts-empty');
    }
    hideElement('posts-table-wrapper');
    if (cardsEl) cardsEl.classList.add('hidden');

    // Show "no results" only when filters are active but no posts match
    if (posts.length > 0 && filtered.length === 0) {
      showElement('posts-table-wrapper');
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:var(--space-2xl); color:var(--color-text-muted)">לא נמצאו פוסטים לפי הסינון הנוכחי</td></tr>`;
      if (cardsEl) {
        cardsEl.classList.remove('hidden');
        cardsEl.innerHTML = `<div class="post-card-empty">לא נמצאו פוסטים לפי הסינון הנוכחי</div>`;
      }
    }
    return;
  }

  hideElement('posts-empty');
  showElement('posts-table-wrapper');
  if (cardsEl) cardsEl.classList.remove('hidden');

  // Sort: newest first (by ID descending)
  const sorted = [...filtered].sort((a, b) => {
    const idA = parseInt(a.id, 10) || 0;
    const idB = parseInt(b.id, 10) || 0;
    return idB - idA;
  });

  // ── Desktop table ──
  tbody.innerHTML = sorted.map(post => {
    const status = (post.status || '').toUpperCase();
    const badge = statusBadge(status);
    const network = networkLabel(post.network);
    const postType = postTypeLabel(post.post_type);
    const publishAt = formatDateTime(post.publish_at);
    const captionIg = truncate(post.caption_ig, 40);
    const captionFb = truncate(post.caption_fb, 40);

    // Thumbnail + file name
    const fileCell = post.drive_file_id
      ? `<div class="cell-file-preview">
           <img class="file-thumbnail" src="/api/drive/thumbnail/${encodeURIComponent(post.drive_file_id)}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">
           <span class="file-thumbnail-fallback" style="display:none">&#128247;</span>
           <span class="file-name-text" title="${escapeHtml(post.drive_file_id)}">${truncate(post.drive_file_id, 14)}</span>
         </div>`
      : '<span style="color:var(--color-text-muted)">-</span>';

    const canEdit = status === 'READY' || status === '';
    const canDelete = status !== 'IN_PROGRESS';

    return `<tr>
      <td>${escapeHtml(post.id || '')}</td>
      <td>${badge}</td>
      <td>${network}</td>
      <td>${postType}</td>
      <td style="direction:ltr; text-align:start">${publishAt}</td>
      <td class="cell-caption ${post.caption_ig ? 'cell-clickable' : ''}" ${post.caption_ig ? `onclick="openCaptionModal('קפשן IG', this.dataset.full)" data-full="${escapeHtml(post.caption_ig)}"` : ''} title="${escapeHtml(post.caption_ig || '')}">${captionIg}</td>
      <td class="cell-caption ${post.caption_fb ? 'cell-clickable' : ''}" ${post.caption_fb ? `onclick="openCaptionModal('קפשן FB', this.dataset.full)" data-full="${escapeHtml(post.caption_fb)}"` : ''} title="${escapeHtml(post.caption_fb || '')}">${captionFb}</td>
      <td class="cell-file">${fileCell}</td>
      <td class="cell-actions">
        ${canEdit ? `<button class="btn btn-ghost btn-sm" onclick="openEditModal(${post._row})" title="עריכה">&#9998;</button>` : ''}
        <button class="btn btn-ghost btn-sm" onclick="duplicatePost(${post._row})" title="שכפול">&#128203;</button>
        ${canDelete ? `<button class="btn btn-ghost btn-sm" onclick="openDeleteConfirm(${post._row}, '${escapeHtml(post.id || '')}')" title="מחיקה" style="color:var(--color-error)">&#128465;</button>` : ''}
        ${post.error ? `<button class="btn btn-ghost btn-sm" onclick="showError(${post._row})" title="פרטי שגיאה" style="color:var(--color-warning)">&#9888;</button>` : ''}
      </td>
    </tr>`;
  }).join('');

  // ── Mobile cards ──
  if (cardsEl) {
    cardsEl.innerHTML = sorted.map(post => {
      const status = (post.status || '').toUpperCase();
      const badge = statusBadge(status);
      const network = networkLabel(post.network);
      const postType = postTypeLabel(post.post_type);
      const publishAt = formatDateTime(post.publish_at);
      const canEdit = status === 'READY' || status === '';
      const canDelete = status !== 'IN_PROGRESS';

      const filePart = post.drive_file_id
        ? `<div class="post-card-divider"></div>
           <div class="post-card-row">
             <span class="post-card-label">קובץ</span>
             <div class="post-card-file">
               <img src="/api/drive/thumbnail/${encodeURIComponent(post.drive_file_id)}" alt="" loading="lazy" onerror="this.style.display='none'">
               <span>${truncate(post.drive_file_id, 20)}</span>
             </div>
           </div>`
        : '';

      const captionIgPart = post.caption_ig
        ? `<div class="post-card-divider"></div>
           <div>
             <span class="post-card-label">קפשן IG</span>
             <div class="post-card-caption" onclick="openCaptionModal('קפשן IG', this.dataset.full)" data-full="${escapeHtml(post.caption_ig)}">${escapeHtml(post.caption_ig)}</div>
           </div>`
        : '';

      const captionFbPart = post.caption_fb
        ? `<div class="post-card-divider"></div>
           <div>
             <span class="post-card-label">קפשן FB</span>
             <div class="post-card-caption" onclick="openCaptionModal('קפשן FB', this.dataset.full)" data-full="${escapeHtml(post.caption_fb)}">${escapeHtml(post.caption_fb)}</div>
           </div>`
        : '';

      return `<div class="post-card">
        <div class="post-card-row">
          <div>${badge}</div>
          <span class="post-card-value" style="color:var(--color-text-muted); font-size:var(--font-size-xs)">#${escapeHtml(post.id || '')}</span>
        </div>
        <div class="post-card-divider"></div>
        <div class="post-card-row">
          <span class="post-card-label">רשת</span>
          <span class="post-card-value">${network}</span>
        </div>
        <div class="post-card-divider"></div>
        <div class="post-card-row">
          <span class="post-card-label">סוג</span>
          <span class="post-card-value">${postType}</span>
        </div>
        <div class="post-card-divider"></div>
        <div class="post-card-row">
          <span class="post-card-label">תאריך פרסום</span>
          <span class="post-card-value" style="direction:ltr">${publishAt}</span>
        </div>
        ${captionIgPart}
        ${captionFbPart}
        ${filePart}
        <div class="post-card-divider"></div>
        <div class="post-card-actions">
          ${canEdit ? `<button class="btn btn-ghost btn-sm" onclick="openEditModal(${post._row})" title="עריכה">&#9998; עריכה</button>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="duplicatePost(${post._row})" title="שכפול">&#128203; שכפול</button>
          ${canDelete ? `<button class="btn btn-ghost btn-sm" onclick="openDeleteConfirm(${post._row}, '${escapeHtml(post.id || '')}')" title="מחיקה" style="color:var(--color-error)">&#128465; מחיקה</button>` : ''}
          ${post.error ? `<button class="btn btn-ghost btn-sm" onclick="showError(${post._row})" title="פרטי שגיאה" style="color:var(--color-warning)">&#9888;</button>` : ''}
        </div>
      </div>`;
    }).join('');
  }
}

function updateStats() {
  const total = posts.length;
  const ready = posts.filter(p => (p.status || '').toUpperCase() === 'READY').length;
  const posted = posts.filter(p => (p.status || '').toUpperCase() === 'POSTED').length;
  const error = posts.filter(p => (p.status || '').toUpperCase() === 'ERROR').length;

  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-ready').textContent = ready;
  document.getElementById('stat-posted').textContent = posted;
  document.getElementById('stat-error').textContent = error;
}

// ─── Shared Form Setup ───────────────────────────────────────
function resetPostForm({ title, rowNumber = '', network = 'IG+FB', postType = 'FEED',
                         publishAt = '', captionIg = '', captionFb = '',
                         driveFileId = '', postId = null } = {}) {
  editPostId = postId;
  document.getElementById('post-modal-title').textContent = title;
  document.getElementById('form-row-number').value = rowNumber;
  document.getElementById('form-network').value = network;
  document.getElementById('form-post-type').value = postType;
  document.getElementById('form-publish-at').value = publishAt;
  document.getElementById('form-caption-ig').value = captionIg;
  document.getElementById('form-caption-fb').value = captionFb;
  document.getElementById('form-drive-file-id').value = driveFileId;
  document.getElementById('form-drive-file-id-manual').value = '';

  if (driveFileId) {
    document.getElementById('selected-file-name').textContent = driveFileId;
    showElement('drive-file-display');
  } else {
    hideElement('drive-file-display');
  }

  hideElement('form-drive-file-id-manual');
  updateCharCounter('ig');
  updateCharCounter('fb');
  openModal('post-modal');
}

// ─── Create Post ─────────────────────────────────────────────
function openCreateModal() {
  resetPostForm({ title: 'פוסט חדש' });
}

// ─── Edit Post ───────────────────────────────────────────────
function openEditModal(rowNumber) {
  const post = posts.find(p => p._row === rowNumber);
  if (!post) return;

  // Convert publish_at to datetime-local format
  let publishAt = '';
  if (post.publish_at) {
    const dt = parseDate(post.publish_at);
    if (dt) {
      const pad = n => String(n).padStart(2, '0');
      publishAt = `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    }
  }

  resetPostForm({
    title: 'עריכת פוסט',
    rowNumber,
    network: post.network || 'IG+FB',
    postType: post.post_type || 'FEED',
    publishAt,
    captionIg: post.caption_ig || '',
    captionFb: post.caption_fb || '',
    driveFileId: post.drive_file_id || '',
    postId: post.id || null,
  });
}

// ─── Duplicate Post ─────────────────────────────────────────
function duplicatePost(rowNumber) {
  const post = posts.find(p => p._row === rowNumber);
  if (!post) return;

  resetPostForm({
    title: 'שכפול פוסט',
    network: post.network || 'IG+FB',
    postType: post.post_type || 'FEED',
    captionIg: post.caption_ig || '',
    captionFb: post.caption_fb || '',
    driveFileId: post.drive_file_id || '',
  });
}

// ─── Save Post (Create or Update) ───────────────────────────
async function savePost() {
  const rowNumber = document.getElementById('form-row-number').value;
  const publishAtInput = document.getElementById('form-publish-at').value;

  // Send the datetime as ISO 8601 with UTC offset so the backend can
  // convert to Israel time correctly regardless of the browser's timezone.
  let publishAt = '';
  if (publishAtInput) {
    const dt = new Date(publishAtInput);
    publishAt = dt.toISOString();
  }

  const data = {
    network: document.getElementById('form-network').value,
    post_type: document.getElementById('form-post-type').value,
    publish_at: publishAt,
    caption_ig: document.getElementById('form-caption-ig').value,
    caption_fb: document.getElementById('form-caption-fb').value,
    drive_file_id: document.getElementById('form-drive-file-id').value,
  };

  // Include expected_id for concurrency-safe updates
  if (rowNumber && editPostId) {
    data.expected_id = editPostId;
  }

  // Validation
  if (!data.publish_at) {
    showToast('יש לבחור תאריך ושעת פרסום', 'error');
    return;
  }
  if (!data.drive_file_id) {
    showToast('יש לבחור קובץ מדיה', 'error');
    return;
  }

  const btn = document.getElementById('btn-save-post');
  btn.disabled = true;
  btn.textContent = 'שומר...';

  try {
    let resp;
    if (rowNumber) {
      // Update
      resp = await fetch(`/api/posts/${rowNumber}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    } else {
      // Create
      resp = await fetch('/api/posts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    }

    const result = await resp.json();

    if (result.error) {
      showToast(result.error, 'error');
      return;
    }

    showToast(rowNumber ? 'הפוסט עודכן בהצלחה' : 'הפוסט נוצר בהצלחה', 'success');
    closePostModal();
    await loadPosts();

  } catch (e) {
    showToast('שגיאה בשמירת הפוסט', 'error');
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'שמירה';
  }
}

function closePostModal() {
  closeModal('post-modal');
}

// ─── Delete Post ─────────────────────────────────────────────
function openDeleteConfirm(rowNumber, postId) {
  deleteRowNumber = rowNumber;
  deletePostId = postId;
  openModal('confirm-modal');
}

function closeConfirmModal() {
  closeModal('confirm-modal');
  deleteRowNumber = null;
  deletePostId = null;
}

async function confirmDelete() {
  if (!deleteRowNumber) return;

  const btn = document.getElementById('btn-confirm-delete');
  btn.disabled = true;
  btn.textContent = 'מוחק...';

  try {
    const deleteUrl = deletePostId
      ? `/api/posts/${deleteRowNumber}?expected_id=${encodeURIComponent(deletePostId)}`
      : `/api/posts/${deleteRowNumber}`;
    const resp = await fetch(deleteUrl, { method: 'DELETE' });
    const result = await resp.json();

    if (result.error) {
      showToast(result.error, 'error');
      return;
    }

    showToast('הפוסט נמחק', 'success');
    closeConfirmModal();
    await loadPosts();

  } catch (e) {
    showToast('שגיאה במחיקת הפוסט', 'error');
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = 'מחיקה';
  }
}

// ─── Show Error Details ──────────────────────────────────────
function showError(rowNumber) {
  const post = posts.find(p => p._row === rowNumber);
  if (!post) return;
  alert(`שגיאה בפוסט #${post.id}:\n\n${post.error || 'אין פרטי שגיאה'}`);
}

// ─── Caption Preview Modal ───────────────────────────────────
function openCaptionModal(title, text) {
  document.getElementById('caption-modal-title').textContent = title;
  document.getElementById('caption-modal-text').textContent = text;
  openModal('caption-modal');
}

function closeCaptionModal() {
  closeModal('caption-modal');
}

async function copyCaptionText() {
  const text = document.getElementById('caption-modal-text').textContent;
  try {
    await navigator.clipboard.writeText(text);
    showToast('הטקסט הועתק', 'success');
  } catch (e) {
    showToast('לא ניתן להעתיק', 'error');
  }
}

// ═══════════════════════════════════════════════════════════════
//  Drive Browser
// ═══════════════════════════════════════════════════════════════

function openDriveBrowser() {
  if (!config.driveFolderId) {
    showToast('לא הוגדרה תיקיית Drive. יש להגדיר GOOGLE_DRIVE_FOLDER_ID.', 'error');
    return;
  }

  selectedDriveFile = null;
  driveStack = [{ folderId: config.driveFolderId, name: 'תיקייה ראשית' }];
  document.getElementById('btn-confirm-drive').disabled = true;
  openModal('drive-modal');
  loadDriveFolder(config.driveFolderId);
}

function closeDriveBrowser() {
  closeModal('drive-modal');
}

async function loadDriveFolder(folderId) {
  const browser = document.getElementById('drive-browser');
  const loading = document.getElementById('drive-loading');
  const empty = document.getElementById('drive-empty');

  browser.innerHTML = '';
  showElement('drive-loading');
  hideElement('drive-empty');

  try {
    const resp = await fetch(`/api/drive/files?folder_id=${encodeURIComponent(folderId)}`);
    const data = await resp.json();

    if (data.error) {
      showToast(data.error, 'error');
      return;
    }

    hideElement('drive-loading');
    const files = data.files || [];

    if (files.length === 0) {
      showElement('drive-empty');
      return;
    }

    // Separate folders and files
    const folders = files.filter(f => f.mimeType === 'application/vnd.google-apps.folder');
    const mediaFiles = files.filter(f => f.mimeType !== 'application/vnd.google-apps.folder');

    // Render folders first
    folders.forEach(f => {
      const el = document.createElement('div');
      el.className = 'drive-file drive-folder';
      el.dataset.folderId = f.id;
      el.dataset.folderName = f.name;
      el.innerHTML = `
        <div class="drive-file-icon">&#128193;</div>
        <div class="drive-file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
      `;
      el.addEventListener('dblclick', () => navigateDriveFolder(f.id, f.name));
      browser.appendChild(el);
    });

    // Render files
    mediaFiles.forEach(f => {
      const el = document.createElement('div');
      el.className = 'drive-file';
      el.dataset.fileId = f.id;
      el.dataset.fileName = f.name;
      const icon = getFileIcon(f.mimeType);
      const thumb = f.thumbnailLink
        ? `<img src="${escapeHtml(f.thumbnailLink)}" alt="${escapeHtml(f.name)}" loading="lazy">`
        : icon;
      el.innerHTML = `
        <div class="drive-file-icon">${thumb}</div>
        <div class="drive-file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
      `;
      el.addEventListener('click', () => selectDriveFile(el, f.id, f.name));
      browser.appendChild(el);
    });

    renderDriveBreadcrumb();

  } catch (e) {
    hideElement('drive-loading');
    showToast('שגיאה בטעינת קבצים מ-Drive', 'error');
    console.error(e);
  }
}

function navigateDriveFolder(folderId, name) {
  driveStack.push({ folderId, name });
  selectedDriveFile = null;
  document.getElementById('btn-confirm-drive').disabled = true;
  loadDriveFolder(folderId);
}

function navigateDriveBreadcrumb(index) {
  driveStack = driveStack.slice(0, index + 1);
  selectedDriveFile = null;
  document.getElementById('btn-confirm-drive').disabled = true;
  loadDriveFolder(driveStack[index].folderId);
}

function renderDriveBreadcrumb() {
  const el = document.getElementById('drive-breadcrumb');
  el.innerHTML = driveStack.map((item, i) => {
    const isLast = i === driveStack.length - 1;
    const link = isLast
      ? `<span style="color:var(--color-text-primary)">${escapeHtml(item.name)}</span>`
      : `<span class="drive-breadcrumb-item" onclick="navigateDriveBreadcrumb(${i})">${escapeHtml(item.name)}</span>`;
    const sep = i < driveStack.length - 1 ? '<span class="drive-breadcrumb-separator">/</span>' : '';
    return link + sep;
  }).join('');
}

function selectDriveFile(el, fileId, fileName) {
  // Deselect previous
  document.querySelectorAll('.drive-file.selected').forEach(e => e.classList.remove('selected'));
  el.classList.add('selected');
  selectedDriveFile = { id: fileId, name: fileName };
  document.getElementById('btn-confirm-drive').disabled = false;
}

function confirmDriveSelection() {
  if (!selectedDriveFile) return;

  document.getElementById('form-drive-file-id').value = selectedDriveFile.id;
  document.getElementById('selected-file-name').textContent = selectedDriveFile.name;
  showElement('drive-file-display');
  hideElement('form-drive-file-id-manual');

  closeDriveBrowser();
}

function clearDriveFile() {
  document.getElementById('form-drive-file-id').value = '';
  document.getElementById('form-drive-file-id-manual').value = '';
  hideElement('drive-file-display');
}

function toggleManualFileId() {
  const el = document.getElementById('form-drive-file-id-manual');
  el.classList.toggle('hidden');
  if (!el.classList.contains('hidden')) {
    el.focus();
  }
}

// ─── Character Counter ──────────────────────────────────────
function updateCharCounter(type) {
  const textarea = document.getElementById(`form-caption-${type}`);
  const counter = document.getElementById(`char-counter-${type}`);
  const countSpan = document.getElementById(`char-count-${type}`);
  if (!textarea || !counter || !countSpan) return;

  const len = textarea.value.length;
  const limit = CHAR_LIMITS[type];
  countSpan.textContent = len.toLocaleString();

  if (len > limit) {
    counter.classList.add('over-limit');
    counter.classList.remove('near-limit');
  } else if (len > limit * 0.9) {
    counter.classList.remove('over-limit');
    counter.classList.add('near-limit');
  } else {
    counter.classList.remove('over-limit', 'near-limit');
  }
}

// ═══════════════════════════════════════════════════════════════
//  Calendar
// ═══════════════════════════════════════════════════════════════

const HEBREW_MONTHS = [
  'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
  'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר'
];

const HEBREW_DAYS = ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳', 'ש׳'];

function renderCalendar() {
  const grid = document.getElementById('calendar-grid');
  const year = calendarDate.getFullYear();
  const month = calendarDate.getMonth();

  document.getElementById('calendar-month-title').textContent =
    `${HEBREW_MONTHS[month]} ${year}`;

  // Day headers (Sunday first for Hebrew calendar)
  let html = HEBREW_DAYS.map(d =>
    `<div class="calendar-day-header">${d}</div>`
  ).join('');

  // First day of month
  const firstDay = new Date(year, month, 1);
  const startDay = firstDay.getDay(); // 0=Sunday

  // Days in month
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  // Previous month padding
  const prevMonthDays = new Date(year, month, 0).getDate();
  for (let i = startDay - 1; i >= 0; i--) {
    html += `<div class="calendar-day other-month">
      <div class="calendar-day-number">${prevMonthDays - i}</div>
    </div>`;
  }

  // Current month days
  const today = new Date();
  for (let day = 1; day <= daysInMonth; day++) {
    const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();

    // Find posts for this day
    const dayPosts = posts.filter(p => {
      if (!p.publish_at) return false;
      const pDate = parseDate(p.publish_at);
      if (!pDate) return false;
      return pDate.getFullYear() === year &&
             pDate.getMonth() === month &&
             pDate.getDate() === day;
    });

    const eventsHtml = dayPosts.slice(0, 3).map(p => {
      const status = (p.status || '').toLowerCase().replace('_', '-').replace(/[^a-z0-9-]/g, '');
      const net = escapeHtml(p.network || '');
      const time = p.publish_at ? formatTime(p.publish_at) : '';
      return `<div class="calendar-event status-${status}" title="${escapeHtml(p.caption_ig || p.caption_fb || '')}">${time} ${net}</div>`;
    }).join('');

    const moreHtml = dayPosts.length > 3
      ? `<div class="calendar-event" style="color:var(--color-text-muted)">+${dayPosts.length - 3} עוד</div>`
      : '';

    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    html += `<div class="calendar-day clickable${isToday ? ' today' : ''}" onclick="openCreateModalWithDate('${dateStr}')">
      <div class="calendar-day-number">${day}</div>
      ${eventsHtml}${moreHtml}
    </div>`;
  }

  // Next month padding
  const totalCells = startDay + daysInMonth;
  const remaining = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
  for (let i = 1; i <= remaining; i++) {
    html += `<div class="calendar-day other-month">
      <div class="calendar-day-number">${i}</div>
    </div>`;
  }

  grid.innerHTML = html;
}

function calendarPrev() {
  calendarDate.setMonth(calendarDate.getMonth() - 1);
  renderCalendar();
}

function calendarNext() {
  calendarDate.setMonth(calendarDate.getMonth() + 1);
  renderCalendar();
}

function calendarToday() {
  calendarDate = new Date();
  renderCalendar();
}

function openCreateModalWithDate(dateStr) {
  resetPostForm({ title: 'פוסט חדש', publishAt: `${dateStr}T12:00` });
}

// ═══════════════════════════════════════════════════════════════
//  View Switching
// ═══════════════════════════════════════════════════════════════

function switchView(view) {
  currentView = view;

  // Toggle nav active
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });

  // Toggle views
  document.getElementById('view-posts').classList.toggle('hidden', view !== 'posts');
  document.getElementById('view-calendar').classList.toggle('hidden', view !== 'calendar');

  if (view === 'calendar') {
    renderCalendar();
  }
}

// ─── Sidebar Toggle ──────────────────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('collapsed');
}

// ═══════════════════════════════════════════════════════════════
//  UI Helpers
// ═══════════════════════════════════════════════════════════════

function openModal(id) {
  document.getElementById(id).classList.add('active');
  document.body.style.overflow = 'hidden';
}

function closeModal(id) {
  document.getElementById(id).classList.remove('active');
  document.body.style.overflow = '';
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-backdrop') && e.target.classList.contains('active')) {
    e.target.classList.remove('active');
    document.body.style.overflow = '';
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.active').forEach(el => {
      el.classList.remove('active');
    });
    document.body.style.overflow = '';
  }
});

function showElement(id) {
  document.getElementById(id).classList.remove('hidden');
}

function hideElement(id) {
  document.getElementById(id).classList.add('hidden');
}

// ─── Toast Notifications ─────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 200);
  }, 4000);
}

// ─── Formatters ──────────────────────────────────────────────
function statusBadge(status) {
  const map = {
    'READY': { class: 'badge-ready', label: 'ממתין' },
    'IN_PROGRESS': { class: 'badge-in-progress', label: 'בתהליך' },
    'POSTED': { class: 'badge-posted', label: 'פורסם' },
    'ERROR': { class: 'badge-error', label: 'שגיאה' },
  };
  const info = map[status] || { class: '', label: escapeHtml(status) || '-' };
  return `<span class="badge ${escapeHtml(info.class)}"><span class="badge-dot"></span>${info.label}</span>`;
}

function networkLabel(network) {
  const map = {
    'IG': 'IG',
    'FB': 'FB',
    'IG+FB': 'IG+FB',
  };
  return map[network] || escapeHtml(network) || '-';
}

function postTypeLabel(type) {
  const map = {
    'FEED': 'פיד',
    'REELS': 'ריל',
  };
  return map[type] || escapeHtml(type) || '-';
}

/**
 * Parse a date string safely across all browsers.
 * Safari requires ISO 8601 format (T separator), so we normalize
 * "YYYY-MM-DD HH:MM" to "YYYY-MM-DDTHH:MM" before parsing.
 */
function parseDate(str) {
  if (!str) return null;
  // Replace first space between date and time with T for ISO 8601 compat
  const normalized = str.replace(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/, '$1T$2');
  const dt = new Date(normalized);
  return isNaN(dt) ? null : dt;
}

function formatDateTime(str) {
  if (!str) return '-';
  const dt = parseDate(str);
  if (!dt) return str;
  const pad = n => String(n).padStart(2, '0');
  return `${pad(dt.getDate())}/${pad(dt.getMonth() + 1)}/${dt.getFullYear()} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function formatTime(str) {
  if (!str) return '';
  const dt = parseDate(str);
  if (!dt) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function truncate(str, max) {
  if (!str) return '<span style="color:var(--color-text-muted)">-</span>';
  return str.length > max ? escapeHtml(str.substring(0, max)) + '...' : escapeHtml(str);
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getFileIcon(mimeType) {
  if (!mimeType) return '&#128196;';
  if (mimeType.startsWith('image/')) return '&#128247;';
  if (mimeType.startsWith('video/')) return '&#127909;';
  if (mimeType === 'application/vnd.google-apps.folder') return '&#128193;';
  return '&#128196;';
}

// ─── Scroll to Top Button ────────────────────────────────────
(function() {
  const btn = document.getElementById('scroll-top-btn');
  if (!btn) return;
  window.addEventListener('scroll', function() {
    btn.classList.toggle('visible', window.scrollY > 300);
  }, { passive: true });
})();
