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

function renderPosts() {
  const tbody = document.getElementById('posts-tbody');

  if (posts.length === 0) {
    showElement('posts-empty');
    hideElement('posts-table-wrapper');
    return;
  }

  hideElement('posts-empty');
  showElement('posts-table-wrapper');

  // Sort: newest publish_at first, then by id descending
  const sorted = [...posts].sort((a, b) => {
    const dateA = parseDate(a.publish_at) || new Date(0);
    const dateB = parseDate(b.publish_at) || new Date(0);
    return dateB - dateA;
  });

  tbody.innerHTML = sorted.map(post => {
    const status = (post.status || '').toUpperCase();
    const badge = statusBadge(status);
    const network = networkLabel(post.network);
    const postType = postTypeLabel(post.post_type);
    const publishAt = formatDateTime(post.publish_at);
    const captionIg = truncate(post.caption_ig, 40);
    const captionFb = truncate(post.caption_fb, 40);
    const fileName = post.drive_file_id ? truncate(post.drive_file_id, 20) : '<span style="color:var(--color-text-muted)">-</span>';

    const canEdit = status === 'READY' || status === '';
    const canDelete = status !== 'IN_PROGRESS';

    return `<tr>
      <td>${escapeHtml(post.id || '')}</td>
      <td>${badge}</td>
      <td>${network}</td>
      <td>${postType}</td>
      <td style="direction:ltr; text-align:start">${publishAt}</td>
      <td class="cell-caption" title="${escapeHtml(post.caption_ig || '')}">${captionIg}</td>
      <td class="cell-caption" title="${escapeHtml(post.caption_fb || '')}">${captionFb}</td>
      <td style="direction:ltr; font-size:12px" title="${escapeHtml(post.drive_file_id || '')}">${fileName}</td>
      <td class="cell-actions">
        ${canEdit ? `<button class="btn btn-ghost btn-sm" onclick="openEditModal(${post._row})" title="עריכה">&#9998;</button>` : ''}
        ${canDelete ? `<button class="btn btn-ghost btn-sm" onclick="openDeleteConfirm(${post._row}, '${escapeHtml(post.id || '')}')" title="מחיקה" style="color:var(--color-error)">&#128465;</button>` : ''}
        ${post.error ? `<button class="btn btn-ghost btn-sm" onclick="showError(${post._row})" title="פרטי שגיאה" style="color:var(--color-warning)">&#9888;</button>` : ''}
      </td>
    </tr>`;
  }).join('');
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

// ─── Create Post ─────────────────────────────────────────────
function openCreateModal() {
  editPostId = null;
  document.getElementById('post-modal-title').textContent = 'פוסט חדש';
  document.getElementById('form-row-number').value = '';
  document.getElementById('form-network').value = 'IG+FB';
  document.getElementById('form-post-type').value = 'FEED';
  document.getElementById('form-publish-at').value = '';
  document.getElementById('form-caption-ig').value = '';
  document.getElementById('form-caption-fb').value = '';
  document.getElementById('form-drive-file-id').value = '';
  document.getElementById('form-drive-file-id-manual').value = '';
  hideElement('drive-file-display');
  hideElement('form-drive-file-id-manual');
  openModal('post-modal');
}

// ─── Edit Post ───────────────────────────────────────────────
function openEditModal(rowNumber) {
  const post = posts.find(p => p._row === rowNumber);
  if (!post) return;

  editPostId = post.id || null;
  document.getElementById('post-modal-title').textContent = 'עריכת פוסט';
  document.getElementById('form-row-number').value = rowNumber;
  document.getElementById('form-network').value = post.network || 'IG+FB';
  document.getElementById('form-post-type').value = post.post_type || 'FEED';

  // Convert publish_at to datetime-local format
  if (post.publish_at) {
    const dt = parseDate(post.publish_at);
    if (dt) {
      const pad = n => String(n).padStart(2, '0');
      document.getElementById('form-publish-at').value =
        `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
    } else {
      document.getElementById('form-publish-at').value = '';
    }
  } else {
    document.getElementById('form-publish-at').value = '';
  }

  document.getElementById('form-caption-ig').value = post.caption_ig || '';
  document.getElementById('form-caption-fb').value = post.caption_fb || '';
  document.getElementById('form-drive-file-id').value = post.drive_file_id || '';

  if (post.drive_file_id) {
    document.getElementById('selected-file-name').textContent = post.drive_file_id;
    showElement('drive-file-display');
  } else {
    hideElement('drive-file-display');
  }

  hideElement('form-drive-file-id-manual');
  openModal('post-modal');
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
  if (!data.caption_ig && !data.caption_fb) {
    showToast('יש למלא לפחות קפשן אחד', 'error');
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

    html += `<div class="calendar-day${isToday ? ' today' : ''}">
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
