import * as THREE from 'three';

const WALL_H  = 2.7;   // standard ceiling height (m)
const WALL_T  = 0.15;  // wall thickness (m)
const FLOOR_T = 0.08;  // floor slab thickness (m)

// Override floor colour by room type
const TYPE_FLOOR = {
  wet:      '#8a9ba8',  // grey-blue tile
  storage:  '#b8b4ae',  // neutral screed
  external: '#9aab8e',  // green-grey concrete pavers
};

let _renderer = null;
let _scene    = null;
let _camera   = null;

export function initRenderer(canvas) {
  // Fixed internal resolution; CSS scales it responsively
  const W = 960, H = 640;
  _renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  _renderer.setSize(W, H, false);
  _renderer.setClearColor(0xffffff);
}

export function buildScene(sceneData) {
  const { rooms, finishes, bounds } = sceneData;

  _scene = new THREE.Scene();
  _scene.background = new THREE.Color(0xffffff);

  // Lighting: strong directional contrast so wall faces read clearly
  _scene.add(new THREE.AmbientLight(0xffffff, 0.35));

  const sun = new THREE.DirectionalLight(0xffffff, 1.1);
  sun.position.set(25, 60, 10);
  _scene.add(sun);

  const fill = new THREE.DirectionalLight(0xb8c8e8, 0.4);
  fill.position.set(-20, 15, 30);
  _scene.add(fill);

  const wallColor  = new THREE.Color(finishes.walls.hex);
  const floorColor = new THREE.Color(finishes.floor.hex);

  for (const room of rooms) {
    _addRoom(room, wallColor, floorColor, finishes);
  }

  // Orthographic isometric camera
  const W = _renderer.domElement.width;
  const H = _renderer.domElement.height;
  const aspect  = W / H;
  const maxDim  = Math.max(bounds.width_m, bounds.depth_m);
  // Tight frustum so model fills the frame
  const frustum = maxDim * 0.58;

  _camera = new THREE.OrthographicCamera(
    -frustum * aspect, frustum * aspect,
     frustum,          -frustum,
    0.1, 1000,
  );

  // Centre of apartment footprint
  const cx = bounds.width_m / 2;
  const cz = bounds.depth_m / 2;
  const d  = maxDim * 1.4;
  _camera.position.set(cx + d, d * 0.7, cz + d);
  _camera.lookAt(cx, WALL_H * 0.3, cz);
}

function _addRoom(room, wallColor, defaultFloor, finishes) {
  const { name, x_m, y_m, width_m, depth_m, is_external, type } = room;

  // Pick floor colour — use hex string directly so THREE.Color parses correctly
  const floorHex = TYPE_FLOOR[type];
  const floorColor = new THREE.Color(floorHex || defaultFloor.getHexString().replace(/^/, '#'));

  // Floor slab
  _box(
    x_m + width_m / 2, -FLOOR_T / 2, y_m + depth_m / 2,
    width_m, FLOOR_T, depth_m,
    new THREE.MeshPhongMaterial({ color: floorColor }),
  );

  const wallH  = is_external ? 0.9 : WALL_H;
  const wallMat = new THREE.MeshPhongMaterial({ color: wallColor });

  // Four perimeter walls
  _wallPanel(x_m,                        y_m,                       width_m, wallH, WALL_T, wallMat); // south
  _wallPanel(x_m,                        y_m + depth_m - WALL_T,    width_m, wallH, WALL_T, wallMat); // north
  _wallPanel(x_m,                        y_m,                       WALL_T,  wallH, depth_m, wallMat); // west
  _wallPanel(x_m + width_m - WALL_T,    y_m,                       WALL_T,  wallH, depth_m, wallMat); // east

  // Kitchen island
  if (type === 'kitchen' && finishes.kitchen_benchtop) {
    const islandMat = new THREE.MeshPhongMaterial({ color: new THREE.Color(finishes.kitchen_benchtop.hex) });
    _box(
      x_m + width_m * 0.50, 0.45, y_m + depth_m * 0.48,
      width_m * 0.40, 0.90, depth_m * 0.30,
      islandMat,
    );
  }

  // Room label (canvas sprite)
  _addLabel(name, x_m + width_m / 2, wallH + 0.3, y_m + depth_m / 2);
}

function _wallPanel(x, z, w, h, d, mat) {
  _box(x + w / 2, h / 2, z + d / 2, w, h, d, mat);
}

function _box(cx, cy, cz, w, h, d, mat) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  mesh.position.set(cx, cy, cz);
  _scene.add(mesh);
}

function _addLabel(text, x, y, z) {
  const canvas = document.createElement('canvas');
  canvas.width = 256; canvas.height = 48;
  const ctx = canvas.getContext('2d');
  ctx.font = 'bold 22px system-ui, sans-serif';
  ctx.fillStyle = '#333333';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 128, 24);

  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(2.5, 0.47, 1);
  sprite.position.set(x, y, z);
  _scene.add(sprite);
}

export function render() {
  if (_renderer && _scene && _camera) {
    _renderer.render(_scene, _camera);
  }
}

export function exportPNG() {
  render();
  return _renderer.domElement.toDataURL('image/png');
}
