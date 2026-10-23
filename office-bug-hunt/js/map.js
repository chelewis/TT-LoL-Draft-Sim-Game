'use strict';
// Office layout: a tile grid with rooms, doors, furniture and interactable stations.

const TILE = 32;
const MAP_W = 48;
const MAP_H = 32;
const T_FLOOR = 0;
const T_WALL = 1;
const T_FURN = 2;

const ROOMS = [
  { name: 'Reception', x0: 1, y0: 1, x1: 11, y1: 9, floor: '#d9d2e3' },
  { name: 'Dev Floor', x0: 13, y0: 1, x1: 30, y1: 9, floor: '#bcc8da' },
  { name: 'Server Room', x0: 32, y0: 1, x1: 46, y1: 9, floor: '#9ea7b3' },
  { name: 'Hallway', x0: 1, y0: 11, x1: 46, y1: 13, floor: '#d3d6dc' },
  { name: 'QA Lab', x0: 1, y0: 15, x1: 11, y1: 30, floor: '#c6d9c6' },
  { name: 'Conference Room', x0: 13, y0: 15, x1: 23, y1: 30, floor: '#d8cab8' },
  { name: 'Break Room', x0: 25, y0: 15, x1: 34, y1: 30, floor: '#e6dbc4' },
  { name: "Manager's Office", x0: 36, y0: 15, x1: 46, y1: 30, floor: '#c9b6a2' },
];

const DOORS = [
  // top rooms -> hallway
  [5, 10], [6, 10], [20, 10], [21, 10], [22, 10], [38, 10], [39, 10],
  // bottom rooms -> hallway
  [5, 14], [6, 14], [17, 14], [18, 14], [19, 14], [28, 14], [29, 14], [40, 14], [41, 14],
  // shortcuts between rooms
  [31, 4], [31, 5], [35, 25], [35, 26], [12, 24], [12, 25],
];

const FURNITURE = [
  { kind: 'desk', x: 3, y: 3, w: 6, h: 1 },
  { kind: 'rack', x: 10, y: 1, w: 1, h: 2 },
  { kind: 'sofa', x: 2, y: 7, w: 4, h: 1 },
  { kind: 'plant', x: 1, y: 1, w: 1, h: 1 },
  { kind: 'desk', x: 15, y: 3, w: 4, h: 1 },
  { kind: 'desk', x: 21, y: 3, w: 4, h: 1 },
  { kind: 'desk', x: 26, y: 3, w: 4, h: 1 },
  { kind: 'desk', x: 15, y: 6, w: 4, h: 1 },
  { kind: 'desk', x: 21, y: 6, w: 4, h: 1 },
  { kind: 'desk', x: 26, y: 6, w: 4, h: 1 },
  { kind: 'rack', x: 34, y: 2, w: 1, h: 5 },
  { kind: 'rack', x: 38, y: 2, w: 1, h: 5 },
  { kind: 'rack', x: 42, y: 2, w: 1, h: 5 },
  { kind: 'bench', x: 3, y: 18, w: 7, h: 1 },
  { kind: 'bench', x: 3, y: 23, w: 7, h: 1 },
  { kind: 'plant', x: 1, y: 30, w: 1, h: 1 },
  { kind: 'table', x: 15, y: 19, w: 7, h: 6 },
  { kind: 'counter', x: 30, y: 15, w: 5, h: 1 },
  { kind: 'table', x: 27, y: 20, w: 2, h: 2 },
  { kind: 'table', x: 31, y: 20, w: 2, h: 2 },
  { kind: 'table', x: 27, y: 25, w: 2, h: 2 },
  { kind: 'plant', x: 34, y: 30, w: 1, h: 1 },
  { kind: 'desk', x: 39, y: 20, w: 5, h: 1 },
  { kind: 'shelf', x: 37, y: 30, w: 9, h: 1 },
  { kind: 'plant', x: 46, y: 15, w: 1, h: 1 },
];

// kind: 'task' = bug ticket, 'rack' = outage repair point, 'button' = emergency standup
const STATIONS = [
  { id: 'kiosk', name: 'Front Desk Kiosk', x: 5, y: 3, kind: 'task' },
  { id: 'alice', name: "Alice's Workstation", x: 16, y: 3, kind: 'task' },
  { id: 'pair', name: 'Pair-Programming Desk', x: 22, y: 3, kind: 'task' },
  { id: 'frontend', name: 'Frontend Desk', x: 27, y: 3, kind: 'task' },
  { id: 'backend', name: 'Backend Desk', x: 16, y: 6, kind: 'task' },
  { id: 'mobile', name: 'Mobile Desk', x: 22, y: 6, kind: 'task' },
  { id: 'hotfix', name: 'Hotfix Desk', x: 28, y: 6, kind: 'task' },
  { id: 'build', name: 'Build Server', x: 34, y: 4, kind: 'task' },
  { id: 'db', name: 'Database Rack', x: 42, y: 4, kind: 'task' },
  { id: 'testbench', name: 'Test Bench', x: 5, y: 18, kind: 'task' },
  { id: 'devicelab', name: 'Device Lab', x: 8, y: 23, kind: 'task' },
  { id: 'projector', name: 'Projector Laptop', x: 21, y: 24, kind: 'task' },
  { id: 'coffee', name: 'Coffee Machine Firmware', x: 32, y: 15, kind: 'task' },
  { id: 'manager', name: "Manager's Laptop", x: 41, y: 20, kind: 'task' },
  { id: 'wiki', name: 'Roadmap Wiki', x: 44, y: 30, kind: 'task' },
  { id: 'rackA', name: 'Prod Server Rack', x: 38, y: 6, kind: 'rack' },
  { id: 'rackB', name: 'Network Closet', x: 10, y: 2, kind: 'rack' },
  { id: 'button', name: 'Standup Bell', x: 18, y: 19, kind: 'button' },
];

const grid = [];
const roomGrid = [];

function buildMap() {
  grid.length = 0;
  roomGrid.length = 0;
  for (let y = 0; y < MAP_H; y++) {
    grid.push(new Array(MAP_W).fill(T_WALL));
    roomGrid.push(new Array(MAP_W).fill(null));
  }
  for (const room of ROOMS) {
    for (let y = room.y0; y <= room.y1; y++) {
      for (let x = room.x0; x <= room.x1; x++) {
        grid[y][x] = T_FLOOR;
        roomGrid[y][x] = room;
      }
    }
  }
  const hallway = ROOMS.find((r) => r.name === 'Hallway');
  for (const [x, y] of DOORS) {
    grid[y][x] = T_FLOOR;
    roomGrid[y][x] = y === 10 || y === 14 ? hallway : null;
  }
  for (const f of FURNITURE) {
    for (let y = f.y; y < f.y + f.h; y++) {
      for (let x = f.x; x < f.x + f.w; x++) grid[y][x] = T_FURN;
    }
  }
}

function isWalkable(tx, ty) {
  return tx >= 0 && ty >= 0 && tx < MAP_W && ty < MAP_H && grid[ty][tx] === T_FLOOR;
}

function isWallTile(tx, ty) {
  return tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H || grid[ty][tx] === T_WALL;
}

function toTile(p) {
  return Math.floor(p / TILE);
}

function tileCenter(t) {
  return t * TILE + TILE / 2;
}

function roomAt(px, py) {
  const tx = toTile(px);
  const ty = toTile(py);
  if (tx < 0 || ty < 0 || tx >= MAP_W || ty >= MAP_H) return null;
  return roomGrid[ty][tx];
}

function roomNameAt(px, py) {
  const r = roomAt(px, py);
  return r ? r.name : 'Hallway';
}

// Walls block sight; furniture does not.
function hasLOS(ax, ay, bx, by) {
  const d = Math.hypot(bx - ax, by - ay);
  const steps = Math.max(1, Math.ceil(d / 8));
  for (let i = 1; i < steps; i++) {
    const x = ax + ((bx - ax) * i) / steps;
    const y = ay + ((by - ay) * i) / steps;
    if (isWallTile(toTile(x), toTile(y))) return false;
  }
  return true;
}

// Breadth-first search over walkable tiles. Returns the list of tiles to walk
// (excluding the start), or null when no tile satisfies isGoal.
function bfsPath(sx, sy, isGoal) {
  if (isGoal(sx, sy)) return [];
  const prev = new Int32Array(MAP_W * MAP_H).fill(-1);
  const start = sy * MAP_W + sx;
  prev[start] = start;
  const queue = [start];
  const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  for (let qi = 0; qi < queue.length; qi++) {
    const cur = queue[qi];
    const cx = cur % MAP_W;
    const cy = (cur - cx) / MAP_W;
    for (const [dx, dy] of dirs) {
      const nx = cx + dx;
      const ny = cy + dy;
      if (!isWalkable(nx, ny)) continue;
      const ni = ny * MAP_W + nx;
      if (prev[ni] !== -1) continue;
      prev[ni] = cur;
      if (isGoal(nx, ny)) {
        const path = [];
        let at = ni;
        while (at !== start) {
          path.push({ x: at % MAP_W, y: Math.floor(at / MAP_W) });
          at = prev[at];
        }
        return path.reverse();
      }
      queue.push(ni);
    }
  }
  return null;
}

function pathToTile(sx, sy, tx, ty) {
  return bfsPath(sx, sy, (x, y) => x === tx && y === ty);
}

function pathToStation(sx, sy, st) {
  return bfsPath(sx, sy, (x, y) => Math.abs(x - st.x) + Math.abs(y - st.y) === 1);
}

function stationById(id) {
  return STATIONS.find((s) => s.id === id);
}

function randomFloorTile(room) {
  for (let i = 0; i < 200; i++) {
    const x = room.x0 + Math.floor(Math.random() * (room.x1 - room.x0 + 1));
    const y = room.y0 + Math.floor(Math.random() * (room.y1 - room.y0 + 1));
    if (isWalkable(x, y)) return { x, y };
  }
  return { x: 24, y: 12 };
}
