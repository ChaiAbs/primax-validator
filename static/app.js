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

function setProgress(pct, stage) {
  pctEl.textContent  = Math.round(pct) + '%';
  fillEl.style.width = Math.round(pct) + '%';
  if (stage) stageEl.textContent = stage;
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
    status.textContent = `✓ ${found.renders} renders · plan ${found.floor_plan ? '✓' : '✗'} · brand ${found.brand ? '✓' : '✗'}`;
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
    }

    // Load renders
    const rendersRes  = await fetch('/api/renders');
    const rendersData = await rendersRes.json();
    const grid = document.getElementById('renders-grid');
    grid.innerHTML = '';
    rendersData.images.forEach(src => {
      const img = document.createElement('img');
      img.src = src;
      grid.appendChild(img);
    });

    // Poll for brand (extracted in background after upload)
    pollBrand();

  } catch (e) {
    status.textContent = 'Upload failed';
    console.error(e);
  }
}

window.handleUpload = e => handleUploadFile(e.files[0]);

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
    if (attempts >= maxAttempts) clearInterval(interval);
  }, 3000);
}

// ── Generate ──────────────────────────────────────────────────────────────────
window.handleGenerate = async function() {
  const btn = document.getElementById('btn-generate');
  btn.disabled    = true;
  btn.textContent = 'Generating...';

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
  setProgress(0, 'Starting pipeline...');
  resize();

  const addLine = (msg, cls = '') => {
    const el = document.createElement('div');
    if (cls) el.className = cls;
    el.textContent = msg;
    log.appendChild(el);
    bar.scrollTop = bar.scrollHeight;
  };

  // Estimate progress from log messages
  let currentPct = 0;
  let hunyuanCrawlTimer = null;

  function startHunyuanCrawl() {
    if (hunyuanCrawlTimer) return; // already running
    // Slowly crawl from currentPct up to 88% over ~4 minutes
    hunyuanCrawlTimer = setInterval(() => {
      if (currentPct < 88) {
        currentPct = Math.min(88, currentPct + 0.3);
        setProgress(currentPct, currentPct < 40 ? 'Submitting to Hunyuan 3D...' :
                                currentPct < 65 ? 'Building 3D model...' :
                                                  'Applying PBR textures...');
      }
    }, 800);
  }

  function stopHunyuanCrawl() {
    if (hunyuanCrawlTimer) { clearInterval(hunyuanCrawlTimer); hunyuanCrawlTimer = null; }
  }

  function estimateProgress(msg) {
    const m = msg.toLowerCase();
    // NanoBanana phase: 0-15% (keyword-driven, fast)
    if (m.includes('geometry') || m.includes('finishes') || m.includes('brand spec') || m.includes('extracting')) {
      return { pct: 5, stage: 'Analysing floor plan...' };
    }
    if (m.includes('nanobanana') || m.includes('nano banana') || (m.includes('render') && m.includes('start'))) {
      return { pct: 8, stage: 'Generating styled render...' };
    }
    if (m.includes('imgbb') || m.includes('hosted') || (m.includes('upload') && !m.includes('hunyuan'))) {
      return { pct: 13, stage: 'Uploading render...' };
    }
    if (m.includes('nb_render') || m.includes('enhanced') || m.includes('saved')) {
      return { pct: 15, stage: 'Styled render complete' };
    }
    // Hunyuan phase: hand off to time-based crawl
    if (m.includes('hunyuan') || m.includes('fal') || m.includes('3d model') || m.includes('in_queue') || m.includes('in_progress')) {
      if (currentPct < 18) return { pct: 18, stage: 'Submitting to Hunyuan 3D...' };
      startHunyuanCrawl();
      return null;
    }
    return null;
  }

  await fetch('/api/generate/start', { method: 'POST' });

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
      stopHunyuanCrawl();
      es.close();
      btn.disabled    = false;
      btn.textContent = 'Generate';
      loadGLB(data.glb_url);

      // Refresh 2D render to show NanoBanana output
      fetch('/api/results').then(r => r.json()).then(d => {
        if (d.image) document.getElementById('plan-img').src = d.image;
      });

      // Load brand
      fetch('/api/brand').then(r => r.json()).then(renderBrand);
    }
    if (data.type === 'error') {
      addLine('✗ ' + data.msg, 'log-error');
      stopHunyuanCrawl();
      es.close();
      btn.disabled    = false;
      btn.textContent = 'Generate';
      stageEl.textContent = 'Pipeline error';
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
