// ── Upload ────────────────────────────────────────────────────────────────────
async function handleUploadFile(file) {
  if (!file) return;

  const attachBtn = document.getElementById('btn-attach');
  if (attachBtn) attachBtn.textContent = 'Uploading...';

  const form = new FormData();
  form.append('file', file);

  try {
    const res  = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) {
      if (attachBtn) attachBtn.textContent = 'Attach Files';
      return;
    }

    const { found, preview, errors } = data;
    if (attachBtn) attachBtn.textContent = 'Attach Files';
    if (errors && errors.length) console.warn('Upload errors:', errors);
    document.getElementById('project-tag').textContent = file.name.replace('.zip', '');
    document.getElementById('btn-generate').classList.remove('hidden');

    // Switch from welcome to workspace
    document.getElementById('welcome-screen').classList.add('hidden');
    document.getElementById('workspace').classList.remove('hidden');

    // Show floor plan
    if (preview) {
      document.getElementById('plan-img').src = preview;
    } else {
      const planFrame = document.querySelector('.plan-frame');
      planFrame.innerHTML = '<span style="font-size:11px;color:rgba(241,240,238,0.3);letter-spacing:0.06em">Floor plan unavailable</span>';
    }

    // Load renders
    const rendersRes  = await fetch('/api/renders');
    const rendersData = await rendersRes.json();
    const grid = document.getElementById('renders-grid');
    grid.innerHTML = '';
    if (rendersData.images && rendersData.images.length) {
      rendersData.images.forEach(src => {
        const img = document.createElement('img');
        img.src = src;
        grid.appendChild(img);
      });
    } else {
      grid.innerHTML = '<span style="font-size:11px;color:rgba(241,240,238,0.3);letter-spacing:0.06em">Renders unavailable</span>';
    }

    // Poll for brand (extracted in background after upload)
    pollBrand();

  } catch (e) {
    if (attachBtn) attachBtn.textContent = 'Attach Files';
    console.error(e);
  }
}

window.handleUpload = e => handleUploadFile(e.files[0]);

// ── Panel swap ────────────────────────────────────────────────────────────────
let _swapped = false;
window.swapPanels = function() {
  const leftCol  = document.querySelector('.left-col');
  const rightCol = document.querySelector('.right-col');
  const panel2d  = document.getElementById('panel-2d');
  const panel3d  = document.getElementById('panel-3d');

  if (!_swapped) {
    rightCol.prepend(panel2d);
    leftCol.prepend(panel3d);
    panel2d.style.height = '100%';
    panel3d.style.height = '';
    panel3d.style.flex   = '0 0 auto';
  } else {
    leftCol.prepend(panel2d);
    rightCol.prepend(panel3d);
    panel2d.style.height = '';
    panel3d.style.height = '100%';
    panel3d.style.flex   = '';
  }
  _swapped = !_swapped;
};

// ── Strip ↔ Main swap ─────────────────────────────────────────────────────────
let _activeStripId = null;

const _titles = {
  'strip-nb':   '2.5D Render',
  'strip-snap': '3D Render',
  'main':       '3D Video',
};

window.handleStripClick = function(imgId, stripId) {
  if (_activeStripId === stripId) {
    swapMainBack();
  } else {
    swapToMain(imgId, stripId);
  }
};

window.swapToMain = function(imgId, stripId) {
  const src = document.getElementById(imgId).src;
  if (!src) return;

  if (_activeStripId && _activeStripId !== stripId) swapMainBack();

  const video       = document.getElementById('output-video');
  const expandedImg = document.getElementById('main-expanded-img');
  const videoSrc    = video.src;

  // Expand image into main
  video.classList.add('hidden');
  expandedImg.src = src;
  expandedImg.classList.remove('hidden');

  // Show mini video in the strip slot
  const stripVideoId = stripId === 'strip-nb' ? 'strip-video-nb' : 'strip-video-snap';
  const stripVideo   = document.getElementById(stripVideoId);
  const stripImg     = document.getElementById(imgId);
  stripVideo.src = videoSrc;
  stripImg.classList.add('hidden');
  stripVideo.classList.remove('hidden');

  // Swap titles
  document.getElementById('title-main').textContent        = _titles[stripId];
  document.getElementById('title-' + stripId).textContent  = _titles['main'];

  _activeStripId = stripId;
};

window.swapMainBack = function() {
  if (!_activeStripId) return;

  const video       = document.getElementById('output-video');
  const expandedImg = document.getElementById('main-expanded-img');

  // Restore main video
  expandedImg.classList.add('hidden');
  expandedImg.src = '';
  video.classList.remove('hidden');

  // Restore strip
  const stripVideoId = _activeStripId === 'strip-nb' ? 'strip-video-nb' : 'strip-video-snap';
  const imgId        = _activeStripId === 'strip-nb' ? 'nb-render-img' : 'snapshot-img';
  document.getElementById(stripVideoId).classList.add('hidden');
  document.getElementById(stripVideoId).src = '';
  document.getElementById(imgId).classList.remove('hidden');

  // Restore titles
  document.getElementById('title-main').textContent             = _titles['main'];
  document.getElementById('title-' + _activeStripId).textContent = _titles[_activeStripId];

  _activeStripId = null;
};

// ── Brand polling ─────────────────────────────────────────────────────────────
function pollBrand() {
  let attempts = 0;
  const maxAttempts = 40;
  const interval = setInterval(async () => {
    attempts++;
    try {
      const res  = await fetch('/api/brand');
      const data = await res.json();
      if (data.brand_identity && (data.brand_identity.brand_name || data.project)) {
        clearInterval(interval);
        renderBrand(data);
      }
    } catch (_) {}
    if (attempts >= maxAttempts) {
      clearInterval(interval);
      document.getElementById('brand-card').innerHTML =
        '<span style="font-size:11px;color:rgba(241,240,238,0.3);letter-spacing:0.06em">Brand unavailable</span>';
    }
  }, 3000);
}

// ── Progress helpers ──────────────────────────────────────────────────────────
const pctEl   = document.getElementById('glb-pct');
const fillEl  = document.getElementById('glb-fill');
const stageEl = document.getElementById('glb-stage');
const quipEl  = document.getElementById('glb-quip');

const _quips = [
  { at: 10, msg: "Reading your floor plan..." },
  { at: 20, msg: "Teaching the AI about your apartment..." },
  { at: 35, msg: "Running multiple renders, picking the best one..." },
  { at: 50, msg: "Halfway there — hang tight." },
  { at: 65, msg: "Validating the output, nearly locked in..." },
  { at: 75, msg: "Handing off to Happy Horse — the cinematic part." },
  { at: 82, msg: "Building your video, this takes a moment..." },
  { at: 88, msg: "Almost there, extracting the perfect frame..." },
  { at: 94, msg: "Wrapping up — shouldn't be long now." },
];
let _lastQuipAt = -1;

function setProgress(pct, stage) {
  pctEl.textContent  = Math.round(pct) + '%';
  fillEl.style.width = Math.round(pct) + '%';
  if (stage) stageEl.textContent = stage;

  const quip = [..._quips].reverse().find(q => pct >= q.at && q.at > _lastQuipAt);
  if (quip) {
    _lastQuipAt = quip.at;
    quipEl.textContent = quip.msg;
  }
}

// ── Video result ──────────────────────────────────────────────────────────────
function showVideoResult(videoUrl, frameUrl, nbImageSrc) {
  document.getElementById('glb-loading').classList.add('hidden');
  document.getElementById('glb-idle').classList.add('hidden');

  document.getElementById('output-video').src  = videoUrl + '?t=' + Date.now();
  document.getElementById('snapshot-img').src   = frameUrl + '?t=' + Date.now();
  if (nbImageSrc) document.getElementById('nb-render-img').src = nbImageSrc;

  document.getElementById('video-result').classList.remove('hidden');
}

// ── Generate ──────────────────────────────────────────────────────────────────
window.handleGenerate = async function() {
  const btn         = document.getElementById('btn-generate');
  const restartBtn  = document.getElementById('btn-restart');
  btn.disabled    = true;
  btn.textContent = 'Generating...';
  restartBtn.classList.add('hidden');

  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  bar.classList.remove('hidden');
  log.innerHTML = '';

  // Show loading state
  document.getElementById('glb-idle').classList.add('hidden');
  document.getElementById('video-result').classList.add('hidden');
  const glbLoading = document.getElementById('glb-loading');
  glbLoading.classList.remove('hidden');
  glbLoading.querySelector('.glb-loading').style.display = '';
  _lastQuipAt = -1;
  if (quipEl) quipEl.textContent = '';
  setProgress(0, 'Starting pipeline...');

  const addLine = (msg, cls = '') => {
    const el = document.createElement('div');
    if (cls) el.className = cls;
    el.textContent = msg;
    log.appendChild(el);
    bar.scrollTop = bar.scrollHeight;
  };

  // Global crawl 0→90% over ~10 min
  let currentPct   = 0;
  let currentStage = 'Starting pipeline...';
  let globalCrawlTimer = null;

  function startGlobalCrawl() {
    if (globalCrawlTimer) return;
    globalCrawlTimer = setInterval(() => {
      if (currentPct < 90) {
        currentPct = Math.min(90, currentPct + 0.12);
        setProgress(currentPct, currentStage);
      }
    }, 800);
  }

  function stopGlobalCrawl() {
    if (globalCrawlTimer) { clearInterval(globalCrawlTimer); globalCrawlTimer = null; }
  }

  function estimateProgress(msg) {
    const m = msg.toLowerCase();
    if (m.includes('extracting') || m.includes('geometry') || m.includes('finishes') || m.includes('brand spec')) {
      currentStage = 'Analysing floor plan...';
      return currentPct < 5 ? { pct: 5, stage: currentStage } : null;
    }
    if (m.includes('parallel')) {
      currentStage = 'Running 3 renders in parallel...';
      return currentPct < 8 ? { pct: 8, stage: currentStage } : null;
    }
    if (m.includes('attempt') && m.includes('done')) {
      currentStage = 'Renders completing...';
      return currentPct < 35 ? { pct: 35, stage: currentStage } : null;
    }
    if (m.includes('all renders done')) {
      currentStage = 'All renders complete';
      return currentPct < 60 ? { pct: 60, stage: currentStage } : null;
    }
    if (m.includes('validating')) {
      currentStage = 'Validating renders...';
      return currentPct < 68 ? { pct: 68, stage: currentStage } : null;
    }
    if (m.includes('best candidate')) {
      currentStage = 'Best render selected';
      return currentPct < 72 ? { pct: 72, stage: currentStage } : null;
    }
    if (m.includes('happy horse') || m.includes('sending best')) {
      currentStage = 'Generating cinematic video...';
      return currentPct < 75 ? { pct: 75, stage: currentStage } : null;
    }
    if (m.includes('video ready') || m.includes('snapshot saved')) {
      currentStage = 'Extracting snapshot frame...';
      return currentPct < 92 ? { pct: 92, stage: currentStage } : null;
    }
    return null;
  }

  await fetch('/api/generate/start', { method: 'POST' });
  startGlobalCrawl();

  let _finished = false;

  function onDone(data) {
    if (_finished) return;
    _finished = true;
    addLine('✓ Done', 'log-done');
    stopGlobalCrawl();
    setProgress(100, 'Done');
    btn.disabled    = false;
    btn.textContent = 'Regenerate';
    restartBtn.classList.remove('hidden');
    fetch('/api/results').then(r => r.json()).then(d => {
      showVideoResult(data.video_url, data.frame_url, d.image || null);
    });
    fetch('/api/brand').then(r => r.json()).then(renderBrand);
  }

  // Fallback poller — kicks in if SSE drops, polls until pipeline finishes
  let _fallbackTimer = null;
  function startFallbackPoll() {
    if (_fallbackTimer || _finished) return;
    _fallbackTimer = setInterval(async () => {
      if (_finished) { clearInterval(_fallbackTimer); return; }
      try {
        const res  = await fetch('/api/generate/status');
        const data = await res.json();
        if (data.result && data.result.type === 'done') {
          clearInterval(_fallbackTimer);
          onDone(data.result);
        } else if (!data.running && !data.result) {
          // pipeline stopped/errored and no result stored
          clearInterval(_fallbackTimer);
          stopGlobalCrawl();
          btn.disabled    = false;
          btn.textContent = 'Regenerate';
          restartBtn.classList.remove('hidden');
          stageEl.textContent = 'Connection lost · click Regenerate to retry';
        }
      } catch (_) {}
    }, 5000);
  }

  const es = new EventSource('/api/generate/stream');
  es.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.type === 'ping') return;
    if (data.type === 'log') {
      addLine(data.msg);
      const est = estimateProgress(data.msg);
      if (est && est.pct > currentPct) {
        currentPct = est.pct;
        setProgress(currentPct, est.stage);
      }
    }
    if (data.type === 'done') {
      es.close();
      onDone(data);
    }
    if (data.type === 'stopped') {
      stopGlobalCrawl();
      es.close();
      _finished = true;
      btn.disabled    = false;
      btn.textContent = 'Regenerate';
      restartBtn.classList.remove('hidden');
      pctEl.textContent   = 'Stopped';
      fillEl.style.width  = '0%';
      stageEl.textContent = 'Pipeline stopped · click Generate to restart';
    }
    if (data.type === 'error') {
      addLine('✗ ' + data.msg, 'log-error');
      stopGlobalCrawl();
      es.close();
      _finished = true;
      btn.disabled    = false;
      btn.textContent = 'Regenerate';
      restartBtn.classList.remove('hidden');
      stageEl.textContent = 'Pipeline error · click Regenerate to retry';
    }
  };
  es.onerror = () => {
    // SSE connection dropped — start fallback poll to catch the result
    startFallbackPoll();
  };
};

// ── Download snapshot ─────────────────────────────────────────────────────────
window.handleDownloadSnapshot = function() {
  const count = Math.max(1, parseInt(document.getElementById('download-count').value) || 1);
  const a = document.createElement('a');
  a.href = `/api/download/snapshot?count=${count}`;
  a.click();
};

function renderBrand(brand) {
  const card = document.getElementById('brand-card');
  const bi   = brand.brand_identity || {};
  const pres = brand.presentation    || {};
  const name = bi.brand_name || brand.project || '';
  if (!name) return;

  const colours = (bi.primary_colours || []).map(c =>
    `<div class="brand-swatch" style="background:${c.hex}" title="${c.name || ''}"></div>`
  ).join('');

  const accents = (pres.accent_colours || []).map(c =>
    `<div class="brand-swatch" style="background:${c.hex}" title="${c.where || ''}"></div>`
  ).join('');

  card.innerHTML = `
    <div class="brand-name">${name}</div>
    <div class="brand-swatches">${colours}${accents}</div>
    <div class="brand-meta">
      ${pres.mood ? `Mood: ${pres.mood}<br/>` : ''}
      ${pres.lighting ? `Lighting: ${pres.lighting}` : ''}
    </div>
  `;
}
