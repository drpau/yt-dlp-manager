const form = document.querySelector('#analyse-form');
const message = document.querySelector('#form-message');
const mediaPanel = document.querySelector('#media-panel');
const jobPanel = document.querySelector('#job-panel');
const browserAccess = document.querySelector('#browser-access');
const fileAccess = document.querySelector('#file-access');
let analysisToken = null;
let analysedUrl = null;
let mode = 'video';
let activeJob = null;
let availableFormats = [];


function sourceValue() { return document.querySelector('input[name="cookie_source"]:checked').value; }
function showMessage(target, text) { target.textContent = text || ''; }
function formatDuration(value) { if (!value) return null; const minutes = Math.floor(value / 60); return `${minutes}:${String(Math.round(value % 60)).padStart(2, '0')}`; }
function formatBytes(bytes) { if (!bytes) return null; return `${(bytes / 1024 / 1024).toFixed(bytes > 100 * 1024 * 1024 ? 0 : 1)} MB`; }

function updateAccess() {
  browserAccess.hidden = sourceValue() !== 'browser';
  fileAccess.hidden = sourceValue() !== 'file';
}
document.querySelectorAll('input[name="cookie_source"]').forEach(input => input.addEventListener('change', updateAccess));

function updateQuality() {
  const select = document.querySelector('#quality');
  const choices = availableFormats.filter(format => format.mode === mode);
  select.replaceChildren(...(choices.length
    ? choices.map(format => new Option(format.label, format.id))
    : [new Option(`No ${mode} formats are available`, '', true, true)]));
  document.querySelector('#download-button').disabled = choices.length === 0;
  document.querySelectorAll('#mode-control button').forEach(button => button.classList.toggle('selected', button.dataset.mode === mode));
}
document.querySelectorAll('#mode-control button').forEach(button => button.addEventListener('click', () => { mode = button.dataset.mode; updateQuality(); }));
updateQuality();

form.addEventListener('submit', async event => {
  event.preventDefault();
  showMessage(message, ''); mediaPanel.hidden = true; jobPanel.hidden = true;
  const submit = form.querySelector('button[type="submit"]'); submit.disabled = true; submit.textContent = 'Analysing…';
  try {
    const response = await fetch('/api/analyse', { method: 'POST', body: new FormData(form) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    analysisToken = data.analysis_token; analysedUrl = form.url.value.trim();
    const media = data.media;
    availableFormats = media.formats || [];
    document.querySelector('#title').textContent = media.title;
    document.querySelector('#source').textContent = media.uploader || media.source || 'Supported source';
    document.querySelector('#details').textContent = [formatDuration(media.duration), media.source].filter(Boolean).join(' · ');
    const thumbnail = document.querySelector('#thumbnail');
    document.querySelector('#thumbnail-wrap').hidden = !media.thumbnail;
    if (media.thumbnail) { thumbnail.src = media.thumbnail; thumbnail.alt = `Thumbnail for ${media.title}`; }
    mediaPanel.hidden = false; updateQuality();
    showMessage(message, data.cookie_file_loaded ? 'cookies.txt loaded for this download. It will be discarded when the job ends.' : '');
    mediaPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) { showMessage(message, error.message); }
  finally { submit.disabled = false; submit.innerHTML = 'Analyse <span aria-hidden="true">→</span>'; }
});

document.querySelector('#download-button').addEventListener('click', async () => {
  if (!analysisToken) return;
  const button = document.querySelector('#download-button'); button.disabled = true;
  try {
    const response = await fetch('/api/jobs', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({analysis_token: analysisToken, url: analysedUrl, mode, format_id: document.querySelector('#quality').value}) });
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    activeJob = data.id; jobPanel.hidden = false; mediaPanel.hidden = true; pollJob();
  } catch (error) { showMessage(message, error.message); button.disabled = false; }
});

async function pollJob() {
  if (!activeJob) return;
  const response = await fetch(`/api/jobs/${activeJob}`); const job = await response.json();
  document.querySelector('#job-title').textContent = job.title || (job.status === 'succeeded' ? 'Download complete' : 'Downloading');
  const pill = document.querySelector('#status-pill'); pill.textContent = job.status; pill.dataset.status = job.status;
  const progress = job.progress || {}; const percent = Math.min(100, Math.round(progress.percent || (job.status === 'succeeded' ? 100 : 0)));
  document.querySelector('#progress-bar').style.width = `${percent}%`;
  document.querySelector('#progress-text').textContent = job.status === 'succeeded'
    ? 'Download complete. Saved in the app’s downloads folder.'
    : job.error || [percent ? `${percent}%` : null, formatBytes(progress.downloaded_bytes), progress.eta ? `${Math.ceil(progress.eta)}s left` : null].filter(Boolean).join(' · ') || 'Waiting to start…';
  showMessage(document.querySelector('#job-message'), job.error || '');
  const done = ['succeeded', 'failed', 'cancelled'].includes(job.status);
  document.querySelector('#cancel-button').hidden = done;
  if (!done) setTimeout(pollJob, 900); else activeJob = null;
}

document.querySelector('#cancel-button').addEventListener('click', async () => { if (activeJob) await fetch(`/api/jobs/${activeJob}/cancel`, {method: 'POST'}); });
