'use strict';
// Office Bug Hunt: simulation, bot AI, standups (meetings) and rendering.

const VISION = 230;
const SPY_VISION = 300;
const KILL_RANGE = 52;
const USE_RANGE = TILE * 1.7;
const REPORT_RANGE = 110;
const PLAYER_SPEED = 165;
const BOT_SPEED = 120;
const RADIUS = 11;
const KILL_COOLDOWN = 25;
const OUTAGE_TIME = 45;
const OUTAGE_COOLDOWN = 60;
const INJECT_COOLDOWN = 35;
const DISCUSS_GAP = 1.3;
const VOTE_TIME = 30;

const PEOPLE = [
  { name: 'Ada', color: '#e74c3c' },
  { name: 'Linus', color: '#3498db' },
  { name: 'Grace', color: '#2ecc71' },
  { name: 'Ken', color: '#f1c40f' },
  { name: 'Margaret', color: '#e67e22' },
  { name: 'Guido', color: '#9b59b6' },
  { name: 'Barbara', color: '#1abc9c' },
  { name: 'Dennis', color: '#ec87c0' },
  { name: 'Brendan', color: '#95a5a6' },
  { name: 'Radia', color: '#8d6e63' },
];
const SKINS = ['#f1c27d', '#e0ac69', '#c68642', '#8d5524', '#ffdbac'];

const SPEED = Math.max(0.1, Math.min(20, Number(new URLSearchParams(location.search).get('speed')) || 1));

const canvas = $('game');
const ctx = canvas.getContext('2d');
const minimap = $('minimap');
const mctx = minimap.getContext('2d');
const keys = new Set();

let G = null;
let mapLayer = null;
let minimapLayer = null;
let viewW = 0;
let viewH = 0;
let showMinimap = true;

const rand = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

// ================================================================ setup

function newGame(opts) {
  buildMap();
  if (!mapLayer) buildMapLayers();

  const people = shuffle(PEOPLE).slice(0, opts.bots + 1);
  const total = people.length;
  const spyCount = Math.min(opts.spies, Math.max(1, Math.floor((total - 1) / 2)));
  let order = shuffle([...Array(total).keys()]);
  if (opts.role === 'spy') order = [0, ...order.filter((i) => i !== 0)];
  if (opts.role === 'dev') order = [...order.filter((i) => i !== 0), 0];
  const spyIds = new Set(order.slice(0, spyCount));

  const spawn = [];
  for (let x = 17; x <= 30; x++) for (let y = 11; y <= 13; y++) spawn.push({ x, y });
  const spots = shuffle(spawn);
  const taskStations = STATIONS.filter((s) => s.kind === 'task');

  const entities = people.map((p, i) => {
    const isPlayer = i === 0;
    const e = {
      id: i,
      name: isPlayer ? opts.name || 'You' : p.name,
      color: p.color,
      skin: pick(SKINS),
      isPlayer,
      isSpy: spyIds.has(i),
      alive: true,
      ejected: false,
      x: tileCenter(spots[i].x),
      y: tileCenter(spots[i].y),
      tasks: shuffle(taskStations).slice(0, opts.tasks).map((st) => ({ station: st, done: false, owner: i, puzzle: null, lockUntil: 0 })),
      path: [],
      goal: null,
      work: 0,
      moving: false,
      facing: 1,
      seen: [],
      susp: {},
      witnessed: [],
      scanT: Math.random() * 0.3,
      reportDelay: -1,
      spottedBody: null,
      killCd: KILL_COOLDOWN * 0.6,
      injectCd: INJECT_COOLDOWN * 0.7,
      huntT: 0,
      repathT: 0,
      lastRoom: 'Hallway',
    };
    return e;
  });

  G = {
    state: 'intro',
    introT: 3.2,
    t: 0,
    entities,
    player: entities[0],
    bodies: [],
    outage: null,
    outageCd: 40,
    emergencyUsed: false,
    meeting: null,
    winner: null,
    hudT: 0,
    clickPath: [],
    playerWork: null,
    splashT: 0,
  };

  showIntro();
}

function showIntro() {
  const p = G.player;
  const spies = G.entities.filter((e) => e.isSpy);
  const mates = spies.filter((e) => !e.isPlayer).map((e) => e.name);
  $('menu').classList.add('hidden');
  $('gameover').classList.add('hidden');
  $('intro').classList.remove('hidden');
  $('intro-text').innerHTML = p.isSpy
    ? `You are a<div class="role spy">SPY</div>Sabotage the release without getting caught.${mates.length ? `<br>Fellow spies: <b>${mates.map(escapeHtml).join(', ')}</b>` : ''}`
    : `You are a<div class="role dev">DEVELOPER</div>There ${spies.length === 1 ? 'is <b>1 spy</b>' : `are <b>${spies.length} spies</b>`} in the office. Fix your bugs and find them.`;
}

function startPlay() {
  G.state = 'play';
  $('intro').classList.add('hidden');
  $('hud').classList.remove('hidden');
  document.querySelectorAll('.spy-only').forEach((el) => el.classList.toggle('hidden', !G.player.isSpy));
  updateHud(true);
}

// ================================================================ helpers

function living() {
  return G.entities.filter((e) => e.alive);
}

function devs() {
  return G.entities.filter((e) => !e.isSpy);
}

function visionOf(e) {
  if (e.isSpy) return SPY_VISION;
  return G.outage ? VISION * 0.65 : VISION;
}

function canSee(viewer, target, radius = visionOf(viewer)) {
  return Math.hypot(viewer.x - target.x, viewer.y - target.y) <= radius && hasLOS(viewer.x, viewer.y, target.x, target.y);
}

function progress() {
  let done = 0;
  let total = 0;
  for (const e of devs()) {
    for (const t of e.tasks) {
      total++;
      if (t.done) done++;
    }
  }
  return { done, total };
}

function setPath(e, path) {
  e.path = path || [];
  return !!path;
}

function entityTile(e) {
  return { x: toTile(e.x), y: toTile(e.y) };
}

function nearestStation(e, filter) {
  let best = null;
  let bestD = USE_RANGE;
  for (const st of STATIONS) {
    if (!filter(st)) continue;
    const d = Math.hypot(e.x - tileCenter(st.x), e.y - tileCenter(st.y));
    if (d <= bestD) {
      best = st;
      bestD = d;
    }
  }
  return best;
}

// ================================================================ movement

function collides(x, y) {
  const x0 = toTile(x - RADIUS);
  const x1 = toTile(x + RADIUS);
  const y0 = toTile(y - RADIUS);
  const y1 = toTile(y + RADIUS);
  for (let ty = y0; ty <= y1; ty++) {
    for (let tx = x0; tx <= x1; tx++) {
      if (isWalkable(tx, ty)) continue;
      const cx = Math.max(tx * TILE, Math.min(x, tx * TILE + TILE));
      const cy = Math.max(ty * TILE, Math.min(y, ty * TILE + TILE));
      if ((x - cx) ** 2 + (y - cy) ** 2 < RADIUS * RADIUS) return true;
    }
  }
  return false;
}

function moveFree(e, dx, dy, ghost) {
  const clampX = (v) => Math.max(RADIUS, Math.min(MAP_W * TILE - RADIUS, v));
  const clampY = (v) => Math.max(RADIUS, Math.min(MAP_H * TILE - RADIUS, v));
  const nx = clampX(e.x + dx);
  if (ghost || !collides(nx, e.y)) e.x = nx;
  const ny = clampY(e.y + dy);
  if (ghost || !collides(e.x, ny)) e.y = ny;
}

// Walks along e.path; returns true once the path is used up.
function followPath(e, speed, dt) {
  let step = speed * dt;
  e.moving = false;
  while (e.path.length && step > 0) {
    const tx = tileCenter(e.path[0].x);
    const ty = tileCenter(e.path[0].y);
    const d = Math.hypot(tx - e.x, ty - e.y);
    if (Math.abs(tx - e.x) > 0.5) e.facing = Math.sign(tx - e.x);
    if (d <= step) {
      e.x = tx;
      e.y = ty;
      e.path.shift();
      step -= d;
    } else {
      e.x += ((tx - e.x) / d) * step;
      e.y += ((ty - e.y) / d) * step;
      step = 0;
    }
    e.moving = true;
  }
  return e.path.length === 0;
}

// ================================================================ update

function update(dt) {
  if (!G) return;
  if (G.splashT > 0) {
    G.splashT -= dt;
    if (G.splashT <= 0) $('splash').classList.add('hidden');
  }
  if (G.state === 'intro') {
    G.introT -= dt;
    if (G.introT <= 0) startPlay();
    return;
  }
  if (G.state === 'meeting') {
    updateMeeting(dt);
    return;
  }
  if (G.state !== 'play') return;

  G.t += dt;
  G.outageCd = Math.max(0, G.outageCd - dt);
  updatePlayer(dt);
  for (const e of G.entities) {
    if (e.isPlayer) continue;
    if (e.isSpy && e.alive) updateSpyBot(e, dt);
    else updateDevBot(e, dt);
    if (G.state !== 'play') return;
  }
  updateOutage(dt);
  if (G.state === 'play') checkWin();

  G.hudT -= dt;
  if (G.hudT <= 0) {
    G.hudT = 0.1;
    updateHud();
  }
}

function updatePlayer(dt) {
  const p = G.player;
  p.killCd = Math.max(0, p.killCd - dt);
  p.injectCd = Math.max(0, p.injectCd - dt);
  p.moving = false;

  if (G.playerWork) {
    // spy pretending to work at a desk
    G.playerWork.t -= dt;
    if (G.playerWork.t <= 0) {
      G.playerWork.entry.done = true;
      toast(`You "finished" ${G.playerWork.entry.station.name}. Nobody suspects a thing.`, 'spy');
      G.playerWork = null;
    }
    return;
  }
  if (isTaskModalOpen()) return;

  let dx = 0;
  let dy = 0;
  if (keys.has('arrowleft') || keys.has('a')) dx -= 1;
  if (keys.has('arrowright') || keys.has('d')) dx += 1;
  if (keys.has('arrowup') || keys.has('w')) dy -= 1;
  if (keys.has('arrowdown') || keys.has('s')) dy += 1;
  const speed = p.alive ? PLAYER_SPEED : PLAYER_SPEED * 1.2;
  if (dx || dy) {
    G.clickPath = [];
    const len = Math.hypot(dx, dy);
    moveFree(p, (dx / len) * speed * dt, (dy / len) * speed * dt, !p.alive);
    if (dx) p.facing = Math.sign(dx);
    p.moving = true;
  } else if (G.clickPath.length) {
    p.path = G.clickPath;
    followPath(p, speed, dt);
    G.clickPath = p.path;
  }
  p.lastRoom = roomNameAt(p.x, p.y);
}

// ---------------------------------------------------------------- dev bots

function updateDevBot(b, dt) {
  const speed = b.alive ? BOT_SPEED : BOT_SPEED * 0.8;

  if (b.alive) perceive(b, dt);
  if (G.state !== 'play') return;

  if (b.work > 0) {
    b.work -= dt;
    b.moving = false;
    if (b.work <= 0) finishWork(b);
    return;
  }
  if (!b.goal) chooseGoal(b);
  if (b.goal && followPath(b, speed, dt)) startWork(b);
  b.lastRoom = roomNameAt(b.x, b.y);
}

function chooseGoal(b) {
  const t = entityTile(b);
  let todo = b.tasks.filter((x) => !x.done);
  if (b.isSpy && !todo.length) {
    b.tasks.forEach((x) => (x.done = false));
    todo = b.tasks;
  }
  if (todo.length && Math.random() < 0.85) {
    const entry = pick(todo);
    if (setPath(b, pathToStation(t.x, t.y, entry.station))) {
      b.goal = { type: b.isSpy ? 'fake' : 'task', entry };
      return;
    }
  }
  const room = pick(ROOMS);
  const dest = randomFloorTile(room);
  if (setPath(b, pathToTile(t.x, t.y, dest.x, dest.y))) b.goal = { type: 'wander' };
}

function startWork(b) {
  const g = b.goal;
  if (!g) return;
  if (g.type === 'task' || g.type === 'fake') b.work = rand(4, 8);
  else if (g.type === 'rack') b.work = 2.5;
  else if (g.type === 'wander') b.work = rand(0.5, 2.5);
  else b.goal = null;
}

function finishWork(b) {
  const g = b.goal;
  b.goal = null;
  if (!g) return;
  if (g.type === 'task') {
    g.entry.done = true;
  } else if (g.type === 'fake') {
    g.entry.done = true;
    if (b.alive && b.injectCd <= 0 && Math.random() < 0.6) injectBug(b);
  } else if (g.type === 'rack' && G.outage && b.alive) {
    fixRack(g.id, b);
  }
}

// Living bots keep track of who they saw where, and notice bodies.
function perceive(b, dt) {
  if (b.reportDelay >= 0) {
    b.reportDelay -= dt;
    if (b.reportDelay < 0 && b.spottedBody && !b.isSpy) {
      callMeeting('report', b, b.spottedBody);
      return;
    }
  }
  b.scanT -= dt;
  if (b.scanT > 0) return;
  b.scanT = 0.3;
  for (const o of G.entities) {
    if (o === b || !o.alive || !canSee(b, o)) continue;
    b.seen.push({ id: o.id, room: roomNameAt(o.x, o.y), t: G.t });
  }
  if (b.seen.length > 400) b.seen = b.seen.filter((s) => s.t > G.t - 60);
  if (!b.isSpy && !b.spottedBody) {
    const body = G.bodies.find((bd) => canSee(b, bd));
    if (body) {
      b.spottedBody = body;
      b.reportDelay = rand(0.4, 1.6);
    }
  }
}

// ---------------------------------------------------------------- spy bots

function updateSpyBot(b, dt) {
  b.killCd = Math.max(0, b.killCd - dt);
  b.injectCd = Math.max(0, b.injectCd - dt);
  perceive(b, dt);

  if (b.killCd <= 0) {
    const target = findKillTarget(b);
    if (target) {
      doKill(b, target);
      if (G.state !== 'play') return;
      b.work = 0;
      b.goal = null;
      b.path = [];
      // leave the scene
      const far = shuffle(b.tasks).find((x) => Math.hypot(tileCenter(x.station.x) - b.x, tileCenter(x.station.y) - b.y) > 300);
      if (far) {
        const t = entityTile(b);
        if (setPath(b, pathToStation(t.x, t.y, far.station))) b.goal = { type: 'fake', entry: far };
      }
      return;
    }
    if ((!b.goal || b.goal.type !== 'hunt') && Math.random() < dt * 0.35) startHunt(b);
  }

  if (!G.outage && G.outageCd <= 0 && Math.random() < dt * 0.02) {
    startOutage(b);
  }

  if (b.goal && b.goal.type === 'hunt') {
    const target = G.entities[b.goal.targetId];
    b.huntT -= dt;
    b.repathT -= dt;
    if (!target.alive || b.huntT <= 0) {
      b.goal = null;
      b.path = [];
    } else {
      if (b.repathT <= 0) {
        b.repathT = 0.8;
        const t = entityTile(b);
        const tt = entityTile(target);
        setPath(b, pathToTile(t.x, t.y, tt.x, tt.y));
      }
      followPath(b, BOT_SPEED * 1.05, dt);
      b.lastRoom = roomNameAt(b.x, b.y);
      return;
    }
  }

  if (b.work > 0) {
    b.work -= dt;
    b.moving = false;
    if (b.work <= 0) finishWork(b);
    return;
  }
  if (!b.goal) chooseGoal(b);
  if (b.goal && followPath(b, BOT_SPEED, dt)) startWork(b);
  b.lastRoom = roomNameAt(b.x, b.y);
}

function witnessesOf(killer, target) {
  return G.entities.filter((o) => o !== killer && o !== target && o.alive && !o.isSpy && (canSee(o, killer) || canSee(o, target)));
}

function findKillTarget(b) {
  for (const o of G.entities) {
    if (!o.alive || o.isSpy) continue;
    if (dist(o, b) > KILL_RANGE || !hasLOS(b.x, b.y, o.x, o.y)) continue;
    if (witnessesOf(b, o).length === 0) return o;
  }
  return null;
}

function startHunt(b) {
  const lonely = G.entities.filter(
    (o) => o.alive && !o.isSpy && !G.entities.some((x) => x !== o && x.alive && !x.isSpy && dist(x, o) < VISION),
  );
  if (!lonely.length) return;
  lonely.sort((a, c) => dist(a, b) - dist(c, b));
  b.goal = { type: 'hunt', targetId: lonely[0].id };
  b.work = 0;
  b.huntT = 15;
  b.repathT = 0;
}

// ================================================================ actions

function doKill(killer, victim) {
  victim.alive = false;
  victim.path = [];
  victim.goal = null;
  victim.work = 0;
  const body = { victimId: victim.id, x: victim.x, y: victim.y, room: roomNameAt(victim.x, victim.y), t: G.t };
  G.bodies.push(body);
  killer.killCd = KILL_COOLDOWN;

  for (const o of G.entities) {
    if (o === killer || !o.alive || o.isPlayer || o.isSpy) continue;
    if (canSee(o, killer) || canSee(o, victim)) {
      o.susp[killer.id] = (o.susp[killer.id] || 0) + 100;
      o.witnessed.push({ killer: killer.id, victim: victim.id, room: body.room });
      o.spottedBody = body;
      o.reportDelay = rand(0.3, 1.0);
    }
  }

  if (victim.isPlayer) {
    closeTaskModal();
    G.clickPath = [];
    splash(`${killer.name} took you offline!<br><small style="font-size:18px">You're a ghost now. You can still fix tickets.</small>`);
  } else if (killer.isPlayer) {
    toast(`You took ${victim.name} offline.`, 'spy');
  }
  checkWin();
}

function splash(html) {
  $('splash-text').innerHTML = html;
  $('splash').classList.remove('hidden');
  G.splashT = 2.6;
}

function injectBug(spy) {
  const done = [];
  for (const e of devs()) for (const t of e.tasks) if (t.done) done.push(t);
  if (!done.length) return false;
  const entry = pick(done);
  entry.done = false;
  entry.puzzle = null;
  spy.injectCd = INJECT_COOLDOWN;
  const owner = G.entities[entry.owner];
  if (owner.isPlayer) {
    toast(`Someone pushed a bad commit! Your ticket at ${entry.station.name} is broken again.`, 'bad');
  } else if (spy.isPlayer) {
    toast(`Bad commit pushed: ${owner.name}'s fix at ${entry.station.name} is broken again.`, 'spy');
  } else {
    toast(`A bad commit just reopened a ticket at ${entry.station.name}.`, 'bad');
  }
  return true;
}

function startOutage(by) {
  G.outage = { t: OUTAGE_TIME, fixed: { rackA: false, rackB: false }, assign: {}, assignT: 0 };
  toast(by.isPlayer ? 'You took production down. Let the chaos begin.' : 'PROD IS DOWN! Fix the Prod Server Rack and the Network Closet!', by.isPlayer ? 'spy' : 'bad');
}

function updateOutage(dt) {
  const o = G.outage;
  if (!o) return;
  o.t -= dt;
  if (o.t <= 0) {
    endGame('spy', 'Production stayed down. The release was cancelled.');
    return;
  }
  o.assignT -= dt;
  if (o.assignT > 0) return;
  o.assignT = 1;
  for (const id of ['rackA', 'rackB']) {
    if (o.fixed[id]) continue;
    const cur = o.assign[id] != null ? G.entities[o.assign[id]] : null;
    if (cur && cur.alive && cur.goal && cur.goal.type === 'rack' && cur.goal.id === id) continue;
    const st = stationById(id);
    const taken = new Set(Object.values(o.assign));
    const helpers = G.entities.filter((e) => e.alive && !e.isPlayer && !e.isSpy && !taken.has(e.id));
    if (!helpers.length) continue;
    helpers.sort((a, c) => Math.hypot(a.x - tileCenter(st.x), a.y - tileCenter(st.y)) - Math.hypot(c.x - tileCenter(st.x), c.y - tileCenter(st.y)));
    const h = helpers[0];
    const t = entityTile(h);
    if (setPath(h, pathToStation(t.x, t.y, st))) {
      h.goal = { type: 'rack', id };
      h.work = 0;
      o.assign[id] = h.id;
    }
  }
}

function fixRack(id, by) {
  const o = G.outage;
  if (!o || o.fixed[id]) return;
  o.fixed[id] = true;
  if (by.isPlayer) toast(`You fixed the ${stationById(id).name}.`, 'good');
  if (o.fixed.rackA && o.fixed.rackB) {
    G.outage = null;
    G.outageCd = OUTAGE_COOLDOWN;
    toast('Production is back up.', 'good');
    for (const e of G.entities) {
      if (e.goal && e.goal.type === 'rack') {
        e.goal = null;
        e.path = [];
        e.work = 0;
      }
    }
  }
}

// ---------------------------------------------------------------- player input actions

function playerUseTarget() {
  const p = G.player;
  if (G.playerWork) return null;
  if (G.outage && p.alive && !p.isSpy) {
    const rack = nearestStation(p, (s) => s.kind === 'rack' && !G.outage.fixed[s.id]);
    if (rack) return { kind: 'rack', station: rack };
  }
  if (p.alive && !G.emergencyUsed && !G.outage) {
    const btn = nearestStation(p, (s) => s.kind === 'button');
    if (btn) return { kind: 'button', station: btn };
  }
  const entryAt = (s) => p.tasks.find((t) => t.station === s && !t.done);
  const st = nearestStation(p, (s) => s.kind === 'task' && (entryAt(s) || (p.isSpy && p.alive)));
  if (st) return { kind: 'task', station: st, entry: entryAt(st) };
  return null;
}

function playerUse() {
  if (G.state !== 'play' || isTaskModalOpen()) return;
  const p = G.player;
  const target = playerUseTarget();
  if (!target) return;
  if (target.kind === 'button') {
    G.emergencyUsed = true;
    callMeeting('emergency', p, null);
    return;
  }
  if (target.kind === 'rack') {
    const st = target.station;
    openTaskModal({
      ticketId: 'INCIDENT · SEV-1',
      title: st.name,
      task: randomRackTask(),
      onSolved: () => fixRack(st.id, p),
      onFailed: () => {},
    });
    return;
  }
  if (p.isSpy) {
    if (p.injectCd <= 0 && injectBug(p)) return;
    if (target.entry) {
      G.playerWork = { entry: target.entry, t: 3 };
      toast(`Pretending to type at ${target.station.name}...`, 'spy');
    } else {
      toast(`Bad commit not ready yet (${Math.ceil(p.injectCd)}s).`, 'spy');
    }
    return;
  }
  const entry = target.entry;
  if (entry.lockUntil > G.t) {
    toast(`Ticket is being reshuffled... ${Math.ceil(entry.lockUntil - G.t)}s`);
    return;
  }
  if (!entry.puzzle) entry.puzzle = randomTask();
  G.clickPath = [];
  openTaskModal({
    ticketId: `BUG-${1000 + STATIONS.indexOf(entry.station) * 37 + entry.owner}`,
    title: entry.station.name,
    task: entry.puzzle,
    onSolved: () => {
      entry.done = true;
      entry.puzzle = null;
      toast(`Ticket closed at ${entry.station.name}.`, 'good');
    },
    onFailed: () => {
      entry.lockUntil = G.t + 3;
      entry.puzzle = randomTask(entry.puzzle);
    },
  });
}

function playerReport() {
  const p = G.player;
  if (G.state !== 'play' || !p.alive) return;
  const body = reportableBody();
  if (body) callMeeting('report', p, body);
}

function reportableBody() {
  const p = G.player;
  return G.bodies.find((b) => Math.hypot(b.x - p.x, b.y - p.y) <= REPORT_RANGE && hasLOS(p.x, p.y, b.x, b.y));
}

function playerKillTarget() {
  const p = G.player;
  if (!p.isSpy || !p.alive || p.killCd > 0) return null;
  let best = null;
  for (const o of G.entities) {
    if (!o.alive || o.isSpy) continue;
    const d = dist(o, p);
    if (d <= KILL_RANGE && hasLOS(p.x, p.y, o.x, o.y) && (!best || d < dist(best, p))) best = o;
  }
  return best;
}

function playerKill() {
  if (G.state !== 'play' || isTaskModalOpen()) return;
  const t = playerKillTarget();
  if (t) doKill(G.player, t);
}

function playerSabotage() {
  const p = G.player;
  if (G.state !== 'play' || !p.isSpy || !p.alive || G.outage || G.outageCd > 0) return;
  startOutage(p);
}

// ================================================================ meetings

function callMeeting(kind, caller, body) {
  if (G.state !== 'play') return;
  closeTaskModal();
  G.playerWork = null;
  G.clickPath = [];
  if (G.outage) {
    G.outage = null;
    G.outageCd = OUTAGE_COOLDOWN;
  }
  G.state = 'meeting';

  const m = {
    kind,
    caller,
    body,
    phase: 'discuss',
    t: 0,
    queue: [],
    shownCount: 0,
    nextMsgT: 0.6,
    votes: {}, // voterId -> targetId | 'skip'
    voteAt: {},
    selected: null,
    accused: false,
    publicAcc: {},
  };
  G.meeting = m;
  prepareSuspicion(m);
  m.queue = buildStatements(m);
  const alive = living();
  for (const e of alive) if (!e.isPlayer) m.voteAt[e.id] = rand(2, VOTE_TIME * 0.7);

  $('meeting-title').textContent = kind === 'report' ? 'Logged-off coworker found!' : 'Emergency standup!';
  $('meeting-sub').textContent =
    kind === 'report'
      ? `${caller.name} found ${G.entities[body.victimId].name} logged off in the ${body.room}.`
      : `${caller.name} rang the Standup Bell.`;
  $('chat-log').innerHTML = '';
  $('meeting').classList.remove('hidden');
  renderMeeting();
}

// Turn what each dev bot saw into suspicion scores.
function prepareSuspicion(m) {
  const deadRooms = G.bodies.map((b) => b.room);
  for (const b of G.entities) {
    if (b.isPlayer || !b.alive || b.isSpy) continue;
    for (const s of b.seen) {
      if (s.id === b.id || !G.entities[s.id].alive) continue;
      if (deadRooms.includes(s.room) && s.t > G.t - 25) b.susp[s.id] = (b.susp[s.id] || 0) + 12;
    }
    // a little noise so bots don't all think alike
    for (const o of G.entities) if (o !== b && o.alive) b.susp[o.id] = (b.susp[o.id] || 0) + rand(0, 8);
  }
}

function lastSeenNear(b, room) {
  const hits = b.seen.filter((s) => s.room === room && s.t > G.t - 25 && G.entities[s.id].alive && s.id !== b.id);
  return hits.length ? G.entities[hits[hits.length - 1].id] : null;
}

function buildStatements(m) {
  const msgs = [];
  const alive = shuffle(living().filter((e) => !e.isPlayer));
  const caller = m.caller;
  if (!caller.isPlayer) {
    msgs.push({
      from: caller,
      text: m.kind === 'report' ? `I found ${G.entities[m.body.victimId].name} in the ${m.body.room}. Who was there?` : 'I called this standup. Something feels off.',
    });
  }
  const witnesses = alive.filter((b) => b.witnessed.length);
  const others = alive.filter((b) => !b.witnessed.length && b !== caller);
  if (caller.witnessed.length && !caller.isPlayer) witnesses.unshift(caller);

  for (const w of witnesses) {
    const ev = w.witnessed[w.witnessed.length - 1];
    const killer = G.entities[ev.killer];
    if (!killer.alive) continue;
    msgs.push({ from: w, text: `I SAW ${killer.name} take ${G.entities[ev.victim].name} offline in the ${ev.room}!`, accuse: killer.id, weight: 55 });
    if (!killer.isPlayer) {
      msgs.push({ from: killer, text: `That's a lie! ${w.name} is trying to frame me.`, accuse: w.id, weight: 15 });
    }
  }
  for (const b of others) {
    if (!b.alive) continue;
    if (b.isSpy) {
      const rooms = ROOMS.map((r) => r.name).filter((r) => !G.bodies.some((bd) => bd.room === r));
      const room = pick(rooms);
      if (Math.random() < 0.3) {
        const scapegoat = pick(living().filter((e) => !e.isSpy && e !== b));
        if (scapegoat) {
          msgs.push({ from: b, text: `${scapegoat.name} has been acting weird all day. Just saying.`, accuse: scapegoat.id, weight: 10 });
          continue;
        }
      }
      msgs.push({ from: b, text: pick([`I was in the ${room}, working on my ticket.`, `${room}. Fixing a null pointer. Wasn't me.`, `I was in the ${room} the whole time.`]) });
      continue;
    }
    const nearBody = m.body ? lastSeenNear(b, m.body.room) : null;
    if (nearBody && Math.random() < 0.8) {
      msgs.push({ from: b, text: `I saw ${nearBody.name} around the ${m.body.room} not long ago.`, accuse: nearBody.id, weight: 15 });
    } else {
      const doing = b.tasks.find((t) => t.done);
      msgs.push({
        from: b,
        text: pick([
          `I was in the ${b.lastRoom}${doing ? `, fixing the ${doing.station.name}` : ''}.`,
          `Not me. I was in the ${b.lastRoom} writing unit tests.`,
          `I didn't see anything. ${b.lastRoom} was quiet.`,
          `Skip unless someone has proof.`,
        ]),
      });
    }
  }
  return msgs;
}

function postChat(from, text, cls = '') {
  const log = $('chat-log');
  const div = document.createElement('div');
  div.className = `msg ${cls}`;
  div.innerHTML = from ? `<b style="color:${from.color}">${escapeHtml(from.name)}:</b>${escapeHtml(text)}` : escapeHtml(text);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

// Spread a public accusation to every dev bot's suspicion.
function applyAccusation(m, accuserId, targetId, weight) {
  m.publicAcc[targetId] = (m.publicAcc[targetId] || 0) + weight;
  for (const b of G.entities) {
    if (b.isPlayer || b.isSpy || !b.alive || b.id === targetId) continue;
    if (b.witnessed.some((w) => w.killer === accuserId)) continue; // they know the accuser is the spy
    b.susp[targetId] = (b.susp[targetId] || 0) + weight;
  }
}

function updateMeeting(dt) {
  const m = G.meeting;
  m.t += dt;
  if (m.phase === 'discuss') {
    m.nextMsgT -= dt;
    if (m.nextMsgT <= 0) {
      if (m.shownCount < m.queue.length) {
        const msg = m.queue[m.shownCount++];
        postChat(msg.from, msg.text);
        if (msg.accuse != null) applyAccusation(m, msg.from.id, msg.accuse, msg.weight);
        m.nextMsgT = DISCUSS_GAP;
      } else {
        m.phase = 'vote';
        m.t = 0;
        postChat(null, 'Voting is open.', 'system');
      }
    }
  } else if (m.phase === 'vote') {
    for (const e of living()) {
      if (e.isPlayer || m.votes[e.id] !== undefined) continue;
      if (m.t >= m.voteAt[e.id]) m.votes[e.id] = botVote(e, m);
    }
    const allVoted = living().every((e) => m.votes[e.id] !== undefined);
    if (allVoted || m.t >= VOTE_TIME) {
      if (G.player.alive && m.votes[G.player.id] === undefined) m.votes[G.player.id] = 'skip';
      tallyVotes(m);
    }
  } else if (m.phase === 'result') {
    if (m.t >= 4) finishMeeting(m);
  }
  renderMeeting();
}

function botVote(b, m) {
  const candidates = living().filter((e) => e !== b);
  if (b.isSpy) {
    const devTargets = candidates.filter((e) => !e.isSpy);
    let best = null;
    for (const e of devTargets) if (!best || (m.publicAcc[e.id] || 0) > (m.publicAcc[best.id] || 0)) best = e;
    if (best && (m.publicAcc[best.id] || 0) >= 10) return best.id;
    return Math.random() < 0.7 ? 'skip' : pick(devTargets).id;
  }
  let best = null;
  for (const e of candidates) if (!best || (b.susp[e.id] || 0) > (b.susp[best.id] || 0)) best = e;
  const score = best ? b.susp[best.id] || 0 : 0;
  if (score >= 40) return best.id;
  if (score >= 20 && Math.random() < 0.4) return best.id;
  return 'skip';
}

function tallyVotes(m) {
  m.phase = 'result';
  m.t = 0;
  const counts = {};
  for (const v of Object.values(m.votes)) counts[v] = (counts[v] || 0) + 1;
  let top = null;
  let topN = 0;
  let tie = false;
  for (const [k, n] of Object.entries(counts)) {
    if (n > topN) {
      top = k;
      topN = n;
      tie = false;
    } else if (n === topN) tie = true;
  }
  if (!top || tie || top === 'skip') {
    m.ejected = null;
    m.resultText = tie ? 'It was a tie. Nobody was let go.' : 'Most people skipped. Nobody was let go.';
  } else {
    const e = G.entities[Number(top)];
    m.ejected = e;
    m.resultText = `${e.name} was let go. ${e.name} ${e.isSpy ? 'WAS' : 'was NOT'} a spy.`;
  }
  postChat(null, m.resultText, 'system');
}

function finishMeeting(m) {
  $('meeting').classList.add('hidden');
  G.meeting = null;
  if (m.ejected) {
    m.ejected.alive = false;
    m.ejected.ejected = true;
  }
  G.bodies = [];
  // everyone regroups around the conference table
  const seats = [];
  for (let x = 14; x <= 22; x++) seats.push({ x, y: 18 }, { x, y: 25 });
  for (let y = 19; y <= 24; y++) seats.push({ x: 14, y }, { x: 22, y });
  const free = shuffle(seats.filter((s) => isWalkable(s.x, s.y)));
  let i = 0;
  for (const e of G.entities) {
    e.path = [];
    e.goal = null;
    e.work = 0;
    e.witnessed = [];
    e.spottedBody = null;
    e.reportDelay = -1;
    if (e.isSpy) e.killCd = Math.max(e.killCd, 15);
    if (e.alive) {
      const s = free[i++ % free.length];
      e.x = tileCenter(s.x);
      e.y = tileCenter(s.y);
    }
  }
  G.clickPath = [];
  G.state = 'play';
  if (m.ejected && m.ejected.isPlayer) toast("You were let go. As a ghost you can still fix tickets.", 'bad');
  checkWin();
}

function renderMeeting() {
  const m = G.meeting;
  if (!m) return;
  const p = G.player;
  const votersFor = {};
  for (const [voter, target] of Object.entries(m.votes)) (votersFor[target] = votersFor[target] || []).push(G.entities[voter]);

  const order = [...G.entities].sort((a, b) => b.alive - a.alive);
  $('vote-cards').innerHTML = order
    .map((e) => {
      const status = e.alive ? '' : e.ejected ? ' <small>(let go)</small>' : ' <small>(offline)</small>';
      const you = e.isPlayer && e.name !== 'You' ? ' <small>(you)</small>' : '';
      const mate = p.isSpy && e.isSpy && !e.isPlayer ? ' spy-mate' : '';
      const voted = m.phase === 'vote' && m.votes[e.id] !== undefined ? '<span class="badge">✔ voted</span>' : '';
      const voters = m.phase === 'result' && votersFor[e.id] ? `<div class="voters">${votersFor[e.id].map((v) => `<i style="background:${v.color}"></i>`).join('')}</div>` : '';
      return `<div class="card${e.alive ? '' : ' dead'}${m.selected === e.id ? ' selected' : ''}${mate}" data-id="${e.id}">
        <div class="avatar" style="background:${e.color}"></div>
        <div><div class="cname">${escapeHtml(e.name)}${you}${status}</div>${voters}</div>${voted}</div>`;
    })
    .join('');
  $('vote-cards').querySelectorAll('.card').forEach((c) => {
    c.onclick = () => {
      const id = Number(c.dataset.id);
      if (!G.entities[id].alive || id === p.id) return;
      m.selected = m.selected === id ? null : id;
      renderMeeting();
    };
  });

  const skipVotes = m.phase === 'result' && votersFor.skip ? ` · ${votersFor.skip.length} skipped` : '';
  if (m.phase === 'discuss') $('meeting-timer').textContent = 'Discussion';
  else if (m.phase === 'vote') $('meeting-timer').textContent = `Vote: ${Math.max(0, Math.ceil(VOTE_TIME - m.t))}s`;
  else $('meeting-timer').textContent = `Results${skipVotes}`;

  const canAct = p.alive && m.votes[p.id] === undefined;
  $('btn-vote').disabled = !(canAct && m.phase === 'vote' && m.selected != null);
  $('btn-skip').disabled = !(canAct && m.phase === 'vote');
  $('btn-accuse').disabled = !(p.alive && !m.accused && m.selected != null && m.phase !== 'result');
  $('meeting-hint').textContent = !p.alive
    ? "Ghosts can't vote. Watch and learn."
    : m.phase === 'discuss'
      ? 'Read the chat. Select someone to accuse them.'
      : m.phase === 'vote'
        ? m.votes[p.id] !== undefined
          ? 'Vote cast. Waiting for the others...'
          : 'Select someone and vote, or skip.'
        : '';
}

$('btn-vote').onclick = () => {
  const m = G && G.meeting;
  if (!m || m.phase !== 'vote' || m.selected == null) return;
  m.votes[G.player.id] = m.selected;
  postChat(null, 'You voted.', 'system');
  renderMeeting();
};
$('btn-skip').onclick = () => {
  const m = G && G.meeting;
  if (!m || m.phase !== 'vote') return;
  m.votes[G.player.id] = 'skip';
  postChat(null, 'You skipped.', 'system');
  renderMeeting();
};
$('btn-accuse').onclick = () => {
  const m = G && G.meeting;
  if (!m || m.selected == null || m.accused) return;
  m.accused = true;
  const target = G.entities[m.selected];
  postChat(G.player, `I think ${target.name} is a spy.`);
  applyAccusation(m, G.player.id, target.id, 22);
  if (!target.isPlayer) {
    const reply = target.isSpy ? `Me?! I was in the ${target.lastRoom}. ${G.player.name} is deflecting.` : `What? I was in the ${target.lastRoom} the whole time!`;
    m.queue.splice(m.shownCount, 0, { from: target, text: reply, accuse: target.isSpy ? G.player.id : undefined, weight: 10 });
    if (m.phase === 'vote') {
      const msg = m.queue[m.shownCount++];
      postChat(msg.from, msg.text);
      if (msg.accuse != null) applyAccusation(m, msg.from.id, msg.accuse, msg.weight);
    }
  }
  renderMeeting();
};

// ================================================================ win / lose

function checkWin() {
  if (G.state !== 'play') return;
  const alive = living();
  const spies = alive.filter((e) => e.isSpy).length;
  const devsAlive = alive.length - spies;
  if (spies === 0) return endGame('dev', 'Every spy was let go. The release ships clean!');
  if (spies >= devsAlive) return endGame('spy', 'The spies now match the devs. Nobody is left to stop them.');
  const pr = progress();
  if (pr.total > 0 && pr.done >= pr.total) return endGame('dev', 'Every bug in the sprint got squashed. Ship it!');
}

function endGame(winner, reason) {
  G.state = 'over';
  G.winner = winner;
  closeTaskModal();
  $('meeting').classList.add('hidden');
  $('hud').classList.add('hidden');
  const won = (winner === 'spy') === G.player.isSpy;
  $('over-title').textContent = `${winner === 'spy' ? 'Spies win' : 'Developers win'}${won ? ' · You won!' : ' · You lost'}`;
  $('over-title').className = winner;
  $('over-reason').textContent = reason;
  $('over-roster').innerHTML = G.entities
    .map((e) => `<div class="${e.isSpy ? 'spy' : ''}"><span style="color:${e.color}">●</span> ${escapeHtml(e.name)}${e.isPlayer && e.name !== 'You' ? ' (you)' : ''} · ${e.isSpy ? 'Spy' : 'Dev'}${e.alive ? '' : ' ✝'}</div>`)
    .join('');
  $('gameover').classList.remove('hidden');
}

// ================================================================ HUD

function updateHud(force) {
  const p = G.player;
  const pr = progress();
  $('progress-fill').style.width = `${pr.total ? (pr.done / pr.total) * 100 : 0}%`;
  $('progress-label').textContent = `Sprint progress: ${pr.done} / ${pr.total} bugs fixed`;
  $('room-label').textContent = roomNameAt(p.x, p.y);

  const rc = $('role-card');
  rc.className = p.isSpy ? 'spy' : 'dev';
  const ghost = p.alive ? '' : ' (ghost)';
  rc.innerHTML = p.isSpy
    ? `SPY${ghost}<small>Take devs offline, push bad commits at desks (E), take prod down.</small>`
    : `DEVELOPER${ghost}<small>Fix your tickets. Report anything suspicious.</small>`;
  const list = p.tasks
    .map((t) => `<li class="${t.done ? 'done' : ''}${p.isSpy ? ' fake' : ''}">${p.isSpy ? '(fake) ' : ''}${escapeHtml(t.station.name)} <span>${escapeHtml(roomNameAt(tileCenter(t.station.x), tileCenter(t.station.y)))}</span></li>`)
    .join('');
  if (force || $('task-list').dataset.html !== list) {
    $('task-list').innerHTML = list;
    $('task-list').dataset.html = list;
  }

  const ob = $('outage-banner');
  if (G.outage) {
    ob.classList.remove('hidden');
    const left = ['rackA', 'rackB'].filter((id) => !G.outage.fixed[id]).map((id) => stationById(id).name);
    ob.textContent = `PROD OUTAGE · ${Math.ceil(G.outage.t)}s · Fix: ${left.join(' + ')}`;
  } else ob.classList.add('hidden');

  const use = playerUseTarget();
  const busy = G.state !== 'play' || isTaskModalOpen();
  $('btn-use').disabled = busy || !use;
  $('btn-use').firstChild.textContent = use ? (use.kind === 'button' ? 'Standup' : use.kind === 'rack' ? 'Repair' : p.isSpy ? (p.injectCd <= 0 ? 'Sabotage' : 'Fake it') : 'Fix bug') : 'Use';
  $('btn-report').disabled = busy || !p.alive || !reportableBody();
  if (p.isSpy) {
    $('btn-kill').disabled = busy || !playerKillTarget();
    $('btn-kill').firstChild.textContent = p.killCd > 0 && p.alive ? `Takedown ${Math.ceil(p.killCd)}` : 'Takedown';
    $('btn-sabotage').disabled = busy || !p.alive || !!G.outage || G.outageCd > 0;
    $('btn-sabotage').firstChild.textContent = G.outageCd > 0 && !G.outage ? `Outage ${Math.ceil(G.outageCd)}` : 'Outage';
  }
}

$('btn-use').onclick = () => playerUse();
$('btn-report').onclick = () => playerReport();
$('btn-kill').onclick = () => playerKill();
$('btn-sabotage').onclick = () => playerSabotage();

// ================================================================ rendering

const FURN_COLORS = {
  desk: '#8a6a4a',
  rack: '#262b35',
  sofa: '#5a6a8a',
  plant: '#3f8f4f',
  bench: '#9aa3ad',
  table: '#7a5a3a',
  counter: '#a7aeb6',
  shelf: '#6a4a2a',
};

function roundRect(c, x, y, w, h, r) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
}

function buildMapLayers() {
  mapLayer = document.createElement('canvas');
  mapLayer.width = MAP_W * TILE;
  mapLayer.height = MAP_H * TILE;
  const c = mapLayer.getContext('2d');
  c.fillStyle = '#1b1f27';
  c.fillRect(0, 0, mapLayer.width, mapLayer.height);
  for (let y = 0; y < MAP_H; y++) {
    for (let x = 0; x < MAP_W; x++) {
      const px = x * TILE;
      const py = y * TILE;
      if (grid[y][x] === T_WALL) {
        c.fillStyle = '#343b4a';
        c.fillRect(px, py, TILE, TILE);
        if (y + 1 < MAP_H && grid[y + 1][x] !== T_WALL) {
          c.fillStyle = '#4d5770';
          c.fillRect(px, py + TILE * 0.55, TILE, TILE * 0.45);
        }
        continue;
      }
      const room = roomGrid[y][x];
      c.fillStyle = room ? room.floor : '#cfd3da';
      c.fillRect(px, py, TILE, TILE);
      c.strokeStyle = 'rgba(0,0,0,0.06)';
      c.strokeRect(px + 0.5, py + 0.5, TILE - 1, TILE - 1);
    }
  }
  for (const f of FURNITURE) {
    const px = f.x * TILE;
    const py = f.y * TILE;
    const w = f.w * TILE;
    const h = f.h * TILE;
    c.fillStyle = 'rgba(0,0,0,0.18)';
    roundRect(c, px + 3, py + 5, w - 2, h - 2, 5);
    c.fill();
    c.fillStyle = FURN_COLORS[f.kind];
    if (f.kind === 'plant') {
      c.fillStyle = '#7a5230';
      c.fillRect(px + 10, py + 18, 12, 12);
      c.fillStyle = FURN_COLORS.plant;
      c.beginPath();
      c.arc(px + 16, py + 14, 11, 0, Math.PI * 2);
      c.fill();
      continue;
    }
    roundRect(c, px + 2, py + 2, w - 4, h - 4, 5);
    c.fill();
    if (f.kind === 'rack') {
      for (let yy = py + 6; yy < py + h - 6; yy += 8) {
        c.fillStyle = '#3a4150';
        c.fillRect(px + 6, yy, w - 12, 5);
      }
    } else if (f.kind === 'desk' || f.kind === 'bench') {
      // monitors along the desk
      for (let xx = px + 6; xx < px + w - 10; xx += TILE) {
        c.fillStyle = '#1d2230';
        c.fillRect(xx + 4, py + 6, 16, 11);
        c.fillStyle = '#4fc3f7';
        c.fillRect(xx + 6, py + 8, 12, 7);
      }
    } else if (f.kind === 'shelf') {
      const colors = ['#c0392b', '#2980b9', '#27ae60', '#f39c12', '#8e44ad'];
      for (let xx = px + 4; xx < px + w - 6; xx += 7) {
        c.fillStyle = colors[(xx / 7) % colors.length | 0];
        c.fillRect(xx, py + 6, 5, h - 12);
      }
    }
  }
  c.font = 'bold 15px system-ui, sans-serif';
  c.textAlign = 'center';
  c.fillStyle = 'rgba(0,0,0,0.22)';
  for (const r of ROOMS) {
    if (r.name === 'Hallway') continue;
    c.fillText(r.name.toUpperCase(), ((r.x0 + r.x1 + 1) / 2) * TILE, (r.y1 + 1) * TILE - 10);
  }

  minimapLayer = document.createElement('canvas');
  minimapLayer.width = MAP_W * 4;
  minimapLayer.height = MAP_H * 4;
  const mc = minimapLayer.getContext('2d');
  for (let y = 0; y < MAP_H; y++) {
    for (let x = 0; x < MAP_W; x++) {
      mc.fillStyle = grid[y][x] === T_WALL ? '#0e1117' : grid[y][x] === T_FURN ? '#555d6e' : '#8a93a6';
      mc.fillRect(x * 4, y * 4, 4, 4);
    }
  }
}

function resize() {
  const dpr = window.devicePixelRatio || 1;
  viewW = window.innerWidth;
  viewH = window.innerHeight;
  canvas.width = Math.floor(viewW * dpr);
  canvas.height = Math.floor(viewH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function render(now) {
  ctx.fillStyle = '#0d1016';
  ctx.fillRect(0, 0, viewW, viewH);
  if (!G || !mapLayer) return;
  const p = G.player;
  const camX = Math.round(p.x - viewW / 2);
  const camY = Math.round(p.y - viewH / 2);
  ctx.save();
  ctx.translate(-camX, -camY);
  ctx.drawImage(mapLayer, 0, 0);

  const pulse = 0.5 + 0.5 * Math.sin(now / 250);
  // stations
  for (const st of STATIONS) {
    const cx = tileCenter(st.x);
    const cy = tileCenter(st.y);
    if (st.kind === 'button') {
      ctx.fillStyle = '#7a1d1d';
      ctx.beginPath();
      ctx.arc(cx, cy, 11, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = G.emergencyUsed ? '#6b6b6b' : `rgb(${200 + 55 * pulse},40,40)`;
      ctx.beginPath();
      ctx.arc(cx, cy - 2, 8, 0, Math.PI * 2);
      ctx.fill();
    } else if (st.kind === 'rack') {
      const broken = G.outage && !G.outage.fixed[st.id];
      for (let i = 0; i < 3; i++) {
        ctx.fillStyle = broken ? (pulse > 0.5 ? '#ff3b3b' : '#5a0d0d') : (Math.floor(now / 300 + i) % 3 ? '#3ee07a' : '#1d5e35');
        ctx.fillRect(cx - 9 + i * 7, cy + 6, 4, 4);
      }
      if (broken) highlightTile(st, '#ff4d4d', pulse);
    } else {
      const mine = p.tasks.find((t) => t.station === st && !t.done);
      if (mine && !p.isSpy) highlightTile(st, '#ffcc4d', pulse);
    }
  }

  // bodies
  for (const b of G.bodies) {
    if (p.alive && !canSee(p, b)) continue;
    drawBody(b);
  }

  // people
  const drawn = G.entities
    .filter((e) => {
      if (e.isPlayer) return true;
      if (!e.alive) return !p.alive && !e.ejected;
      return !p.alive || canSee(p, e);
    })
    .sort((a, b) => a.y - b.y);
  for (const e of drawn) drawPerson(e, now);

  ctx.restore();

  // fog of war
  if (p.alive) {
    const r = visionOf(p);
    const g = ctx.createRadialGradient(viewW / 2 + (p.x - camX - viewW / 2), viewH / 2 + (p.y - camY - viewH / 2), r * 0.55, p.x - camX, p.y - camY, r);
    g.addColorStop(0, 'rgba(8,10,16,0)');
    g.addColorStop(1, 'rgba(8,10,16,0.78)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, viewW, viewH);
  }
  if (G.outage) {
    ctx.fillStyle = `rgba(255,0,0,${0.06 + 0.08 * pulse})`;
    ctx.fillRect(0, 0, viewW, viewH);
  }

  drawMinimap(pulse);
}

function highlightTile(st, color, pulse) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2 + 2 * pulse;
  ctx.globalAlpha = 0.6 + 0.4 * pulse;
  roundRect(ctx, st.x * TILE - 2, st.y * TILE - 2, TILE + 4, TILE + 4, 6);
  ctx.stroke();
  ctx.restore();
}

function drawPerson(e, now) {
  const ghost = !e.alive;
  const bob = e.moving ? Math.sin(now / 80 + e.id) * 2 : 0;
  const x = e.x;
  const y = e.y + bob;
  ctx.save();
  if (ghost) ctx.globalAlpha = 0.45;
  if (!ghost) {
    ctx.fillStyle = 'rgba(0,0,0,0.25)';
    ctx.beginPath();
    ctx.ellipse(e.x, e.y + 13, 11, 4, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  // torso (shirt color is the identity)
  ctx.fillStyle = e.color;
  roundRect(ctx, x - 10, y - 4, 20, 17, 6);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // badge lanyard
  ctx.fillStyle = '#fff';
  ctx.fillRect(x - 2 + e.facing * 3, y + 3, 5, 6);
  // head
  ctx.fillStyle = e.skin;
  ctx.beginPath();
  ctx.arc(x, y - 10, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  // hair
  ctx.fillStyle = '#2b2118';
  ctx.beginPath();
  ctx.arc(x, y - 12, 8, Math.PI, Math.PI * 2);
  ctx.fill();
  // eyes
  ctx.fillStyle = '#111';
  ctx.fillRect(x + e.facing * 3 - 1, y - 10, 2, 2);
  ctx.fillRect(x + e.facing * 3 - 5 * (e.facing > 0 ? 1 : -1) - 1, y - 10, 2, 2);
  if (ghost) {
    ctx.fillStyle = '#fff';
    ctx.font = '12px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('👻', x + 12, y - 16);
  }
  // name tag
  ctx.font = 'bold 12px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(0,0,0,0.75)';
  const label = e.isPlayer && e.name !== 'You' ? `${e.name} (you)` : e.name;
  ctx.strokeText(label, x, y - 23);
  ctx.fillStyle = G.player.isSpy && e.isSpy ? '#ff6b81' : '#fff';
  ctx.fillText(label, x, y - 23);
  if (e.isPlayer && !ghost) {
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(e.x, e.y + 13, 15, 6, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function drawBody(b) {
  const e = G.entities[b.victimId];
  ctx.save();
  // spilled coffee
  ctx.fillStyle = 'rgba(92,58,30,0.7)';
  ctx.beginPath();
  ctx.ellipse(b.x + 14, b.y + 8, 10, 5, 0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.translate(b.x, b.y);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = e.color;
  roundRect(ctx, -10, -4, 20, 17, 6);
  ctx.fill();
  ctx.fillStyle = e.skin;
  ctx.beginPath();
  ctx.arc(0, -10, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  ctx.save();
  ctx.font = 'bold 13px system-ui';
  ctx.textAlign = 'center';
  ctx.fillStyle = '#111';
  ctx.fillText('x x', b.x - 10, b.y + 4);
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(0,0,0,0.75)';
  ctx.strokeText(`${e.name} (offline)`, b.x, b.y - 20);
  ctx.fillStyle = '#ff8080';
  ctx.fillText(`${e.name} (offline)`, b.x, b.y - 20);
  ctx.restore();
}

function drawMinimap(pulse) {
  if (!showMinimap || !minimapLayer || window.innerWidth <= 720) return;
  const s = minimap.width / (MAP_W * TILE);
  mctx.clearRect(0, 0, minimap.width, minimap.height);
  mctx.drawImage(minimapLayer, 0, 0, minimap.width, minimap.height);
  const p = G.player;
  for (const t of p.tasks) {
    if (t.done || p.isSpy) continue;
    mctx.fillStyle = '#ffcc4d';
    mctx.fillRect(tileCenter(t.station.x) * s - 2.5, tileCenter(t.station.y) * s - 2.5, 5, 5);
  }
  if (G.outage) {
    for (const id of ['rackA', 'rackB']) {
      if (G.outage.fixed[id]) continue;
      const st = stationById(id);
      mctx.fillStyle = pulse > 0.5 ? '#ff3b3b' : '#7a1010';
      mctx.fillRect(tileCenter(st.x) * s - 3, tileCenter(st.y) * s - 3, 6, 6);
    }
  }
  mctx.fillStyle = p.color;
  mctx.strokeStyle = '#fff';
  mctx.beginPath();
  mctx.arc(p.x * s, p.y * s, 3.5, 0, Math.PI * 2);
  mctx.fill();
  mctx.stroke();
}

// ================================================================ input + loop

window.addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (k === 'escape') {
    closeTaskModal();
    return;
  }
  if (!G || G.state !== 'play') return;
  if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(k)) e.preventDefault();
  keys.add(k);
  if (e.repeat) return;
  if (k === 'e') playerUse();
  else if (k === 'r') playerReport();
  else if (k === 'q') playerKill();
  else if (k === 'x') playerSabotage();
  else if (k === 'm') {
    showMinimap = !showMinimap;
    minimap.classList.toggle('hidden', !showMinimap);
  }
});
window.addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
window.addEventListener('blur', () => keys.clear());
window.addEventListener('resize', resize);

canvas.addEventListener('pointerdown', (e) => {
  if (!G || G.state !== 'play' || isTaskModalOpen() || G.playerWork) return;
  const p = G.player;
  const wx = e.clientX + p.x - viewW / 2;
  const wy = e.clientY + p.y - viewH / 2;
  const tx = toTile(wx);
  const ty = toTile(wy);
  const start = entityTile(p);
  let path = isWalkable(tx, ty) ? pathToTile(start.x, start.y, tx, ty) : null;
  // clicking a desk walks up to it
  if (!path && tx >= 0 && ty >= 0 && tx < MAP_W && ty < MAP_H && grid[ty][tx] === T_FURN) {
    path = bfsPath(start.x, start.y, (x, y) => Math.abs(x - tx) + Math.abs(y - ty) === 1);
  }
  G.clickPath = path || [];
});

$('btn-start').onclick = () => {
  newGame({
    name: $('opt-name').value.trim().slice(0, 12) || 'You',
    bots: Number($('opt-bots').value),
    spies: Number($('opt-spies').value),
    role: $('opt-role').value,
    tasks: Number($('opt-tasks').value),
  });
};
$('btn-again').onclick = () => {
  $('gameover').classList.add('hidden');
  $('hud').classList.add('hidden');
  $('menu').classList.remove('hidden');
  G = null;
};

let lastTime = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - lastTime) / 1000) * SPEED;
  lastTime = now;
  update(dt);
  render(now);
  requestAnimationFrame(frame);
}

resize();
requestAnimationFrame(frame);
