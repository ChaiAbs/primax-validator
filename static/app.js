import * as THREE from 'three';
import { GLTFLoader }    from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ── GLB viewer ────────────────────────────────────────────────────────────────
const canvas     = document.getElementById('glb-canvas');
const viewerHint = document.getElementById('viewer-hint');
const glbLoading = document.getElementById('glb-loading');   // the viewer-frame card
const glbIdle    = document.getElementById('glb-idle');
const pctEl      = document.getElementById('glb-pct');
const fillEl     = document.getElementById('glb-fill');
const stageEl    = document.getElementById('glb-stage');
const quipEl     = document.getElementById('glb-quip');

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.shadowMap.enabled   = true;
renderer.shadowMap.type      = THREE.PCFSoftShadowMap;
renderer.toneMapping         = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
renderer.outputColorSpace    = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1718);

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
camera.position.set(0, 5, 8);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.5));
const sun = new THREE.DirectionalLight(0xfff5e0, 3);
sun.position.set(5, 10, 5);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
scene.add(sun);
const fill = new THREE.DirectionalLight(0xd0e8ff, 0.8);
fill.position.set(-5, 3, -5);
scene.add(fill);

function resize() {
  const w = glbLoading.clientWidth, h = glbLoading.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);

const loader = new GLTFLoader();

const _quips = [
  { at: 10,  msg: "Reading your floor plan..." },
  { at: 20,  msg: "Teaching the AI about your apartment..." },
  { at: 35,  msg: "Running multiple renders, picking the best one..." },
  { at: 50,  msg: "Halfway there — hang tight." },
  { at: 65,  msg: "Validating the output, nearly locked in..." },
  { at: 75,  msg: "Handing off to Hunyuan 3D — the slow part." },
  { at: 82,  msg: "Building geometry, this takes a moment..." },
  { at: 88,  msg: "Almost there, just applying textures..." },
  { at: 94,  msg: "Wrapping up — shouldn't be long now." },
];
let _lastQuipAt = -1;

function setProgress(pct, stage) {
  pctEl.textContent  = Math.round(pct) + '%';
  fillEl.style.width = Math.round(pct) + '%';
  if (stage) stageEl.textContent = stage;

  // Show quip when crossing a threshold
  const quip = [..._quips].reverse().find(q => pct >= q.at && q.at > _lastQuipAt);
  if (quip) {
    _lastQuipAt = quip.at;
    quipEl.textContent = quip.msg;
  }
}

function loadGLB(url) {
  // Make sure viewer-frame is visible, canvas still hidden until load complete
  glbIdle.classList.add('hidden');
  glbLoading.classList.remove('hidden');
  canvas.classList.add('hidden');
  viewerHint.classList.add('hidden');
  setProgress(95, 'Loading 3D model...');
  resize();

  loader.load(url + '?t=' + Date.now(),
    gltf => {
      scene.children.filter(c => c.userData.isModel).forEach(c => scene.remove(c));
      const model = gltf.scene;
      model.userData.isModel = true;

      const box    = new THREE.Box3().setFromObject(model);
      const centre = box.getCenter(new THREE.Vector3());
      const size   = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);
      const scale  = 6 / maxDim;

      model.scale.setScalar(scale);
      model.position.sub(centre.multiplyScalar(scale));
      scene.add(model);

      // Hide loading overlay, reveal canvas
      document.querySelector('.glb-loading').style.display = 'none';
      canvas.classList.remove('hidden');
      viewerHint.classList.remove('hidden');
      setProgress(100, 'Done');

      const dist = maxDim * scale * 1.2;
      camera.position.set(dist * 0.7, dist * 0.8, dist * 0.7);
      controls.target.set(0, 0, 0);
      controls.update();
      resize();
    },
    xhr => {
      if (xhr.lengthComputable) {
        const pct = 95 + Math.round((xhr.loaded / xhr.total) * 5);
        setProgress(pct, 'Loading 3D model...');
      }
    },
    err => {
      stageEl.textContent = 'Failed to load GLB';
      console.error(err);
    }
  );
}

(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();

// ── Upload ────────────────────────────────────────────────────────────────────
async function handleUploadFile(file) {
  if (!file) return;

  const status = document.getElementById('upload-status');
  status.textContent = 'Uploading...';

  const form = new FormData();
  form.append('file', file);

  try {
    const res  = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) { status.textContent = 'Error: ' + data.error; return; }

    const { found, preview, errors } = data;
    status.textContent = '';
    if (errors && errors.length) console.warn('Upload errors:', errors);
    document.getElementById('project-tag').textContent = file.name.replace('.zip', '');
    document.getElementById('btn-generate').classList.remove('hidden');

    // Switch from welcome to workspace
    document.getElementById('welcome-screen').classList.add('hidden');
    document.getElementById('workspace').classList.remove('hidden');
    setTimeout(resize, 50);

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
    status.textContent = 'Upload failed';
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
    // Move 2D into right col (top), 3D into left col (top)
    rightCol.prepend(panel2d);
    leftCol.prepend(panel3d);
    panel2d.style.height = '100%';
    panel3d.style.height = '';
    panel3d.style.flex   = '0 0 auto';
  } else {
    // Restore — 2D back to left col top, 3D back to right col
    leftCol.prepend(panel2d);
    rightCol.prepend(panel3d);
    panel2d.style.height = '';
    panel3d.style.height = '100%';
    panel3d.style.flex   = '';
  }
  _swapped = !_swapped;
  resize();
};

// ── Brand polling ─────────────────────────────────────────────────────────────
function pollBrand() {
  let attempts = 0;
  const maxAttempts = 40; // up to ~2 min
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

// ── Generate ──────────────────────────────────────────────────────────────────
window.handleStop = async function() {
  await fetch('/api/generate/stop', { method: 'POST' });
  document.getElementById('btn-stop').disabled = true;
  document.getElementById('btn-stop').textContent = 'Stopping...';
};

window.handleGenerate = async function() {
  const btn     = document.getElementById('btn-generate');
  const stopBtn = document.getElementById('btn-stop');
  btn.disabled    = true;
  btn.textContent = 'Generating...';
  stopBtn.classList.remove('hidden');
  stopBtn.disabled    = false;
  stopBtn.textContent = 'Stop';

  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  bar.classList.remove('hidden');
  log.innerHTML = '';

  // Show loading state in 3D panel
  glbIdle.classList.add('hidden');
  glbLoading.classList.remove('hidden');
  document.querySelector('.glb-loading').style.display = '';  // ensure visible
  canvas.classList.add('hidden');
  viewerHint.classList.add('hidden');
  _lastQuipAt = -1;
  if (quipEl) quipEl.textContent = '';
  setProgress(0, 'Starting pipeline...');
  resize();

  const addLine = (msg, cls = '') => {
    const el = document.createElement('div');
    if (cls) el.className = cls;
    el.textContent = msg;
    log.appendChild(el);
    bar.scrollTop = bar.scrollHeight;
  };

  // Global crawl — runs entire pipeline, ~10 min total = 600s
  // Crawls 0 → 90% over 600s = 0.15%/s = 0.12% per 800ms tick
  let currentPct = 0;
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
    // Use keywords only to update the stage label and nudge forward if behind
    if (m.includes('extracting') || m.includes('geometry') || m.includes('finishes') || m.includes('brand spec')) {
      currentStage = 'Analysing floor plan...';
      return currentPct < 5 ? { pct: 5, stage: currentStage } : null;
    }
    if (m.includes('attempt 1')) {
      currentStage = 'Generating render (1/3)...';
      return currentPct < 8 ? { pct: 8, stage: currentStage } : null;
    }
    if (m.includes('attempt 2')) {
      currentStage = 'Generating render (2/3)...';
      return currentPct < 28 ? { pct: 28, stage: currentStage } : null;
    }
    if (m.includes('attempt 3')) {
      currentStage = 'Generating render (3/3)...';
      return currentPct < 48 ? { pct: 48, stage: currentStage } : null;
    }
    if (m.includes('validating')) {
      currentStage = 'Validating renders...';
      return currentPct < 68 ? { pct: 68, stage: currentStage } : null;
    }
    if (m.includes('best candidate')) {
      currentStage = 'Best render selected';
      return currentPct < 72 ? { pct: 72, stage: currentStage } : null;
    }
    if (m.includes('hunyuan') || m.includes('submitting to hunyuan')) {
      currentStage = 'Submitting to Hunyuan 3D...';
      return currentPct < 75 ? { pct: 75, stage: currentStage } : null;
    }
    if (m.includes('in_queue') || m.includes('in_progress') || m.includes('building')) {
      currentStage = 'Building 3D model...';
      return null;
    }
    if (m.includes('pbr') || m.includes('texture')) {
      currentStage = 'Applying PBR textures...';
      return null;
    }
    return null;
  }

  await fetch('/api/generate/start', { method: 'POST' });
  startGlobalCrawl();

  const es = new EventSource('/api/generate/stream');
  es.onmessage = e => {
    const data = JSON.parse(e.data);
    if (data.type === 'ping')  return;
    if (data.type === 'log') {
      addLine(data.msg);
      const est = estimateProgress(data.msg);
      if (est && est.pct > currentPct) {
        currentPct = est.pct;
        setProgress(currentPct, est.stage);
      }
    }
    if (data.type === 'done') {
      addLine('✓ Done', 'log-done');
      stopGlobalCrawl();
      es.close();
      btn.disabled    = false;
      btn.textContent = 'Generate';
      stopBtn.classList.add('hidden');
      loadGLB(data.glb_url);

      // Refresh 2D render to show NanoBanana output
      fetch('/api/results').then(r => r.json()).then(d => {
        if (d.image) document.getElementById('plan-img').src = d.image;
      });

      // Load brand
      fetch('/api/brand').then(r => r.json()).then(renderBrand);
    }
    if (data.type === 'stopped') {
      stopGlobalCrawl();
      es.close();
      btn.disabled    = false;
      btn.textContent = 'Generate';
      stopBtn.classList.add('hidden');
      pctEl.textContent   = 'Stopped';
      fillEl.style.width  = '0%';
      stageEl.textContent = 'Pipeline stopped · click Generate to restart';
    }
    if (data.type === 'error') {
      addLine('✗ ' + data.msg, 'log-error');
      stopGlobalCrawl();
      es.close();
      btn.disabled    = false;
      btn.textContent = 'Generate';
      stopBtn.classList.add('hidden');
      stageEl.textContent = 'Pipeline error · click Generate to restart';
    }
  };
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
