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

// 0–50% = NB stage · 50–100% = HH stage
const _quips = [
  { at:  5, msg: "Reading your floor plan..." },
  { at: 15, msg: "Teaching the AI about your apartment..." },
  { at: 30, msg: "Running 3 renders in parallel..." },
  { at: 45, msg: "Picking the best result..." },
  { at: 50, msg: "Halfway there — 2.5D render complete." },
  { at: 62, msg: "Sending to Happy Horse..." },
  { at: 75, msg: "Building your video, this takes a moment..." },
  { at: 88, msg: "Almost there, extracting the perfect frame..." },
  { at: 94, msg: "Wrapping up — shouldn't be long now." },
];
let _lastQuipAt = -1;

function setProgress(pct, stage) {
  const rounded = Math.round(pct);
  pctEl.textContent  = rounded + '%';
  fillEl.style.width = rounded + '%';
  if (stage) stageEl.textContent = stage;

  // Sync in-main loading (HH stage)
  const vmlPct  = document.getElementById('vml-pct');
  const vmlFill = document.getElementById('vml-fill');
  if (vmlPct)  vmlPct.textContent  = rounded + '%';
  if (vmlFill) vmlFill.style.width = rounded + '%';

  const quip = [..._quips].reverse().find(q => pct >= q.at && q.at > _lastQuipAt);
  if (quip) {
    _lastQuipAt = quip.at;
    if (quipEl) quipEl.textContent = quip.msg;
    const vmlQuip = document.getElementById('vml-quip');
    if (vmlQuip) vmlQuip.textContent = quip.msg;
  }
}

// ── Video result ──────────────────────────────────────────────────────────────
function showVideoResult(videoUrl, frameUrl, nbImageSrc) {
  document.getElementById('glb-loading').classList.add('hidden');
  document.getElementById('glb-idle').classList.add('hidden');

  // Restore full result layout
  document.getElementById('nb-main-img').classList.add('hidden');
  document.getElementById('video-main-loading').classList.add('hidden');
  document.getElementById('output-video').classList.remove('hidden');
  document.getElementById('output-video').src = videoUrl + '?t=' + Date.now();
  document.getElementById('snapshot-img').src  = frameUrl + '?t=' + Date.now();
  if (nbImageSrc) document.getElementById('nb-render-img').src = nbImageSrc;

  document.getElementById('strip-mini-progress').classList.add('hidden');
  document.getElementById('title-strip-nb').classList.remove('hidden');
  document.getElementById('strip-nb').classList.remove('hidden');
  document.getElementById('strip-hh-section').classList.remove('hidden');
  document.getElementById('title-main').textContent = '3D Video';

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

  // NB stage: crawl 0→45% · snaps to 50 on nb_done
  let currentPct   = 0;
  let currentStage = 'Starting pipeline...';
  let globalCrawlTimer = null;

  function startGlobalCrawl(maxPct, speed = 0.12) {
    if (globalCrawlTimer) return;
    globalCrawlTimer = setInterval(() => {
      if (currentPct < maxPct) {
        currentPct = Math.min(maxPct, currentPct + speed);
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
      return currentPct < 10 ? { pct: 10, stage: currentStage } : null;
    }
    if (m.includes('attempt') && m.includes('done')) {
      currentStage = 'Renders completing...';
      return currentPct < 25 ? { pct: 25, stage: currentStage } : null;
    }
    if (m.includes('all') && m.includes('done')) {
      currentStage = 'All renders complete';
      return currentPct < 38 ? { pct: 38, stage: currentStage } : null;
    }
    if (m.includes('validating')) {
      currentStage = 'Validating renders...';
      return currentPct < 42 ? { pct: 42, stage: currentStage } : null;
    }
    if (m.includes('best candidate')) {
      currentStage = 'Best render selected';
      return currentPct < 48 ? { pct: 48, stage: currentStage } : null;
    }
    return null;
  }

  await fetch('/api/generate/start', { method: 'POST' });
  startGlobalCrawl(45);

  let _finished = false;

  function onNbDone() {
    if (_finished) return;
    _finished = true;
    addLine('✓ 2.5D render ready', 'log-done');
    stopGlobalCrawl();
    currentPct = 50;
    setProgress(50, '2.5D render complete');
    btn.disabled    = false;
    btn.textContent = 'Regenerate';
    document.getElementById('btn-continue').classList.remove('hidden');
    document.getElementById('btn-regen-video').classList.add('hidden');
    restartBtn.classList.remove('hidden');
    fetch('/api/results').then(r => r.json()).then(d => {
      // Show 2.5D big in main tile
      if (d.image) {
        document.getElementById('nb-main-img').src = d.image;
        document.getElementById('nb-main-img').classList.remove('hidden');
      }
      document.getElementById('output-video').classList.add('hidden');
      document.getElementById('main-expanded-img').classList.add('hidden');
      document.getElementById('title-main').textContent = '2.5D Render';
      // Mini progress (50%) in strip, hide NB thumbnail (it's big now)
      document.getElementById('strip-mini-progress').classList.remove('hidden');
      document.getElementById('title-strip-nb').classList.add('hidden');
      document.getElementById('strip-nb').classList.add('hidden');
      // Hide 3D render / snapshot / download until video is ready
      document.getElementById('strip-hh-section').classList.add('hidden');
      document.getElementById('glb-loading').classList.add('hidden');
      document.getElementById('glb-idle').classList.add('hidden');
      document.getElementById('video-result').classList.remove('hidden');
    });
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
        if (data.result && data.result.type === 'nb_done') {
          clearInterval(_fallbackTimer);
          onNbDone();
        } else if (!data.running && !data.result) {
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
    if (data.type === 'nb_done') {
      es.close();
      onNbDone();
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
    startFallbackPoll();
  };
};

// ── 3D Snapshot ───────────────────────────────────────────────────────────────
let _capturedFrameDataUrl = null;

window.handleCapture3D = function() {
  const video = document.getElementById('output-video');
  if (!video.src) return;

  const canvas = document.createElement('canvas');
  canvas.width  = video.videoWidth  || 1280;
  canvas.height = video.videoHeight || 720;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);

  _capturedFrameDataUrl = canvas.toDataURL('image/png');

  // Update the 3D render thumbnail
  const snapImg = document.getElementById('snapshot-img');
  snapImg.src = _capturedFrameDataUrl;
};

// ── Regenerate Video ──────────────────────────────────────────────────────────
window.handleRegenVideo = async function() {
  const btn = document.getElementById('btn-regen-video');
  btn.disabled    = true;
  btn.textContent = 'Regenerating...';

  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  bar.classList.remove('hidden');
  log.innerHTML = '';

  // Show in-main loading, hide video
  document.getElementById('output-video').classList.add('hidden');
  document.getElementById('video-main-loading').classList.remove('hidden');
  _lastQuipAt = 50;
  let regenPct = 50;
  setProgress(50, 'Sending to Happy Horse...');

  await fetch('/api/generate/video', { method: 'POST' });

  let crawlTimer = setInterval(() => {
    if (regenPct < 95) { regenPct = Math.min(95, regenPct + 0.10); setProgress(regenPct, stageEl.textContent); }
  }, 800);

  const es = new EventSource('/api/generate/stream');
  es.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.type === 'ping') return;
    if (data.type === 'log') {
      const el = document.createElement('div');
      el.textContent = data.msg;
      log.appendChild(el);
      bar.scrollTop = bar.scrollHeight;
      const m = data.msg.toLowerCase();
      if ((m.includes('video ready') || m.includes('downloading')) && regenPct < 75) {
        regenPct = 75; setProgress(regenPct, 'Downloading video...');
      }
      if (m.includes('extracting frame') && regenPct < 90) {
        regenPct = 90; setProgress(regenPct, 'Extracting snapshot frame...');
      }
    }
    if (data.type === 'done') {
      clearInterval(crawlTimer);
      es.close();
      setProgress(100, 'Done');
      btn.disabled    = false;
      btn.textContent = 'Regenerate Video';
      document.getElementById('video-main-loading').classList.add('hidden');
      document.getElementById('output-video').classList.remove('hidden');
      document.getElementById('output-video').src = data.video_url + '?t=' + Date.now();
      document.getElementById('snapshot-img').src = data.frame_url + '?t=' + Date.now();
      _capturedFrameDataUrl = null;
    }
    if (data.type === 'error') {
      clearInterval(crawlTimer);
      es.close();
      btn.disabled    = false;
      btn.textContent = 'Regenerate Video';
      document.getElementById('video-main-loading').classList.add('hidden');
      document.getElementById('output-video').classList.remove('hidden');
      const el = document.createElement('div');
      el.className   = 'log-error';
      el.textContent = '✗ ' + data.msg;
      log.appendChild(el);
    }
  };
};

// ── Continue (Stage 2: Happy Horse) ──────────────────────────────────────────
window.handleContinue = async function() {
  const continueBtn = document.getElementById('btn-continue');
  const regenBtn    = document.getElementById('btn-generate');
  const restartBtn  = document.getElementById('btn-restart');
  continueBtn.disabled    = true;
  continueBtn.textContent = 'Generating...';
  regenBtn.disabled       = true;

  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  bar.classList.remove('hidden');
  log.innerHTML = '';

  const addLine = (msg, cls = '') => {
    const el = document.createElement('div');
    if (cls) el.className = cls;
    el.textContent = msg;
    log.appendChild(el);
    bar.scrollTop = bar.scrollHeight;
  };

  // Move 2.5D from main tile into strip thumbnail — keep video-result open
  const nbMainImg = document.getElementById('nb-main-img');
  if (nbMainImg.src) document.getElementById('nb-render-img').src = nbMainImg.src;
  nbMainImg.classList.add('hidden');
  document.getElementById('strip-mini-progress').classList.add('hidden');
  document.getElementById('title-strip-nb').classList.remove('hidden');
  document.getElementById('strip-nb').classList.remove('hidden');
  document.getElementById('strip-hh-section').classList.add('hidden');
  document.getElementById('output-video').classList.add('hidden');
  document.getElementById('title-main').textContent = '3D Video';

  // Show in-main loading overlay (video-result stays open so strip remains visible)
  document.getElementById('video-main-loading').classList.remove('hidden');

  // Pick up progress from 50%
  let hhPct = 50;
  _lastQuipAt = 50;
  if (quipEl) quipEl.textContent = '';
  setProgress(50, 'Sending to Happy Horse...');

  await fetch('/api/generate/continue', { method: 'POST' });

  // Crawl 50→95%
  let crawlTimer = setInterval(() => {
    if (hhPct < 95) {
      hhPct = Math.min(95, hhPct + 0.10);
      setProgress(hhPct, stageEl.textContent);
    }
  }, 800);

  const es = new EventSource('/api/generate/stream');
  es.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.type === 'ping') return;
    if (data.type === 'log') {
      addLine(data.msg);
      const m = data.msg.toLowerCase();
      if ((m.includes('happy horse') || m.includes('submitting')) && hhPct < 58) {
        hhPct = 58; setProgress(hhPct, 'Generating cinematic video...');
      }
      if ((m.includes('video ready') || m.includes('downloading')) && hhPct < 75) {
        hhPct = 75; setProgress(hhPct, 'Downloading video...');
      }
      if (m.includes('extracting frame') && hhPct < 90) {
        hhPct = 90; setProgress(hhPct, 'Extracting snapshot frame...');
      }
    }
    if (data.type === 'done') {
      clearInterval(crawlTimer);
      es.close();
      setProgress(100, 'Done');
      addLine('✓ Done', 'log-done');
      continueBtn.disabled = false;
      continueBtn.classList.add('hidden');
      regenBtn.disabled    = false;
      restartBtn.classList.remove('hidden');
      document.getElementById('btn-regen-video').classList.remove('hidden');
      fetch('/api/results').then(r => r.json()).then(d => {
        showVideoResult(data.video_url, data.frame_url, d.image || null);
      });
    }
    if (data.type === 'error') {
      clearInterval(crawlTimer);
      es.close();
      continueBtn.disabled    = false;
      continueBtn.textContent = 'Continue';
      regenBtn.disabled       = false;
      addLine('✗ ' + data.msg, 'log-error');
      stageEl.textContent = 'Error · click Continue to retry';
      // Restore 2.5D-in-main state so user can retry Continue
      document.getElementById('video-main-loading').classList.add('hidden');
      document.getElementById('nb-main-img').classList.remove('hidden');
      document.getElementById('strip-mini-progress').classList.remove('hidden');
      document.getElementById('title-strip-nb').classList.add('hidden');
      document.getElementById('strip-nb').classList.add('hidden');
      document.getElementById('title-main').textContent = '2.5D Render';
    }
  };
  es.onerror = () => { clearInterval(crawlTimer); };
};

// ── Download snapshot ─────────────────────────────────────────────────────────
window.handleDownloadSnapshot = async function() {
  const count = Math.max(1, parseInt(document.getElementById('download-count').value) || 1);
  const btn   = document.querySelector('.download-row .btn');

  function triggerDownload(url, filename) {
    const a = document.createElement('a');
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  btn.disabled   = true;
  btn.innerHTML  = '<span class="btn-spinner"></span>';

  try {
    if (_capturedFrameDataUrl) {
      const res  = await fetch('/api/download/snapshot-data', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ data: _capturedFrameDataUrl, count }),
      });
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      triggerDownload(url, count > 1 ? `3d_renders_${count}x.zip` : '3d_render.png');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } else {
      const res  = await fetch(`/api/download/snapshot?count=${count}`);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      triggerDownload(url, count > 1 ? `3d_renders_${count}x.zip` : '3d_render.png');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
  } finally {
    btn.disabled    = false;
    btn.innerHTML = 'Download';
  }
};

function renderBrand(brand) {
  const card = document.getElementById('brand-card');
  const bi   = brand.brand_identity || {};
  const pres = brand.presentation    || {};
  const name = bi.brand_name || brand.project || '';
  if (!name) return;

  const allColours = [
    ...(bi.primary_colours || []).map(c => ({ hex: c.hex, label: c.name || c.hex })),
    ...(pres.accent_colours || []).map(c => ({ hex: c.hex, label: c.where || c.name || c.hex })),
  ];

  const swatchRows = allColours.map(c => `
    <div class="brand-swatch-row">
      <div class="brand-swatch" style="background:${c.hex}"></div>
      <span class="brand-swatch-label">${c.label}</span>
    </div>`
  ).join('');

  card.innerHTML = `
    <div class="brand-name">${name}</div>
    <div class="brand-swatches-vertical">${swatchRows}</div>
    <div class="brand-meta">
      ${pres.mood ? `Mood: ${pres.mood}<br/>` : ''}
      ${pres.lighting ? `Lighting: ${pres.lighting}` : ''}
    </div>
  `;
}
