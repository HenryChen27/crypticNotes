// ============================================================
// 合成大水母 — Core Game Logic
// ============================================================

(function () {
  'use strict';

  // --- Aliases ---
  const { Engine, Bodies, Events, Composite, Sleeping } = Matter;

  // ============================================================
  // Utility
  // ============================================================
  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

  function lerp(a, b, t) { return a + (b - a) * t; }

  function weightedPick(values, weights) {
    const total = weights.reduce((s, w) => s + w, 0);
    let r = Math.random() * total;
    for (let i = 0; i < values.length; i++) {
      r -= weights[i];
      if (r <= 0) return values[i];
    }
    return values[values.length - 1];
  }

  function pickNextLevel() {
    return weightedPick([1, 2, 3, 4, 5], [35, 30, 20, 10, 5]);
  }

  // ============================================================
  // Game State
  // ============================================================
  const G = {
    phase: 'loading',         // loading | title | countdown | transition | playing | gameover
    paused: false,
    pauseTime: 0,
    runId: null,
    bubbleTransition: null,
    score: 0,
    totalScore: 0,

    // Jellyfish tracking
    items: [],                // { id, level, body, sprite, w, h, visualScale, isMerging }
    nextId: 0,

    // Merge animations
    merges: [],               // { phase, progress, a, b, midX, midY, newLevel, newItem }

    // Clip / drop
    clipX: 1295,              // center of clip range
    dropLevel: null,          // level currently on the clip (null = 轮空)
    nextLevel: 1,             // level after the current drop (shown in preview)
    isDragging: false,
    keys: { left: false, right: false },
    canDrop: true,
    dropCooldownTimer: null,

    // Game over
    overflowStart: null,

    // Timing
    countdownEnd: 0,
    countdownStart: 0,
    countdownCue: -1,
    lastTime: 0,
    physicsAccumulator: 0,

    // Physics
    engine: null,
    walls: [],

    // Assets
    assets: null,

    // Canvas
    canvas: null,
    ctx: null,

    // Drop preview ghost alpha
    ghostAlpha: 0.5,

    // Appearance animation timestamps (-1 = not animating)
    clipAppearStart: -1,
    nextAppearStart: -1,

    // Periodic merge scan
    lastMergeScan: 0,
  };

  // ============================================================
  // Physics
  // ============================================================
  function initPhysics() {
    G.engine = Engine.create({
      enableSleeping: true,
      gravity: { x: CONFIG.PHYSICS.gravity.x, y: CONFIG.PHYSICS.gravity.y },
    });
    // Increase solver iterations for more stable stacking (default: pos=6, vel=4)
    G.engine.positionIterations = 15;
    G.engine.velocityIterations = 8;

    // Matter 0.18 records speed before collision resolution. With our strong
    // gravity this includes each step's falling impulse even at rest, preventing
    // sleep. Refresh motion from the resolved Verlet state for the next step.
    Events.on(G.engine, 'afterUpdate', () => {
      for (const body of Composite.allBodies(G.engine.world)) {
        if (body.isStatic || body.isSleeping) continue;
        body.velocity.x = body.position.x - body.positionPrev.x;
        body.velocity.y = body.position.y - body.positionPrev.y;
        body.angularVelocity = body.angle - body.anglePrev;
        const speedScale = (1000 / 60) / CONFIG.PHYSICS.fixedDelta;
        body.speed = Math.hypot(body.velocity.x, body.velocity.y) * speedScale;
        body.angularSpeed = Math.abs(body.angularVelocity) * speedScale;
      }
    });

    const C = CONFIG.CONTAINER;
    const t = CONFIG.PHYSICS.wallThickness;
    const wallOpts = {
      isStatic: true,
      restitution: 0,
      friction: 0.3,
      label: 'wall',
    };

    const wallH = C.bottom + 400; // extend wall far above container
    const wallY = (-200 + C.bottom) / 2;

    const left = Bodies.rectangle(C.left - t / 2, wallY, t, wallH + t, wallOpts);
    const right = Bodies.rectangle(C.right + t / 2, wallY, t, wallH + t, wallOpts);
    const bottom = Bodies.rectangle(
      (C.left + C.right) / 2, C.bottom + t / 2, C.right - C.left + t, t,
      { ...wallOpts, label: 'floor' }
    );

    G.walls = [left, right, bottom];
    Composite.add(G.engine.world, G.walls);
  }

  // ============================================================
  // Jellyfish Body Factory
  // ============================================================
  function createJellyfishBody(x, y, level) {
    const def = CONFIG.JELLYFISH[level - 1];
    // A merged fish is larger than its parents. Keep its full collision shape
    // inside the walls/floor at birth so overlap cannot eject it out of the bin.
    const radius = Math.max(def.width, def.height) / 2;
    x = clamp(x, CONFIG.CONTAINER.left + radius, CONFIG.CONTAINER.right - radius);
    y = Math.min(y, CONFIG.CONTAINER.bottom - radius);
    const opts = {
      restitution: CONFIG.PHYSICS.restitution,
      friction: CONFIG.PHYSICS.friction,
      frictionStatic: CONFIG.PHYSICS.frictionStatic,
      // Matter 0.18 applies air drag once per step, so preserve the 60Hz drag.
      frictionAir: 1 - Math.pow(1 - CONFIG.PHYSICS.frictionAir,
        CONFIG.PHYSICS.fixedDelta / (1000 / 60)),
      density: CONFIG.PHYSICS.density,
      sleepThreshold: CONFIG.PHYSICS.sleepThreshold,
      label: `fish_${level}`,
    };

    let body;
    if (def.type === 'circle') {
      const r = Math.max(def.width, def.height) / 2;
      // Matter's default circles have only 10–26 sides. Small polygon corners
      // keep rocking in a crowded pile, so use a consistent smooth outline.
      body = Bodies.polygon(x, y, CONFIG.PHYSICS.circleSegments, r, opts);
      body.circleRadius = r;
    } else {
      // Ellipse: approximate with polygon vertices
      const rx = def.width / 2;
      const ry = def.height / 2;
      const segs = CONFIG.PHYSICS.ellipseSegments;
      const verts = [];
      for (let i = 0; i < segs; i++) {
        const a = (i / segs) * Math.PI * 2 - Math.PI / 2;
        verts.push({ x: rx * Math.cos(a), y: ry * Math.sin(a) });
      }
      try {
        body = Bodies.fromVertices(x, y, [verts], opts);
      } catch (e) {
        // Fallback to circle
        body = Bodies.circle(x, y, Math.max(rx, ry), opts);
      }
      if (!body) {
        body = Bodies.circle(x, y, Math.max(rx, ry), opts);
      }
    }

    body.jellyfishLevel = level;
    return body;
  }

  // ============================================================
  // Jellyfish Management
  // ============================================================
  function addJellyfishItem(body, level) {
    const def = CONFIG.JELLYFISH[level - 1];
    const item = {
      id: G.nextId++,
      level,
      body,
      sprite: G.assets.images[`fish${level}`],
      w: def.width,
      h: def.height,
      visualScale: 1,
      isMerging: false,
      previousPose: { x: body.position.x, y: body.position.y, angle: body.angle },
      breathPhase: Math.random() * Math.PI * 2,
      spawnTime: performance.now(),
      bodyInWorld: false,   // tracks whether body is added to physics world
    };
    G.items.push(item);
    return item;
  }

  function removeJellyfishItem(body) {
    const idx = G.items.findIndex(it => it.body === body);
    if (idx !== -1) {
      G.items.splice(idx, 1);
    }
    // Also remove from physics world if present
    if (Composite.allBodies(G.engine.world).includes(body)) {
      Composite.remove(G.engine.world, body);
    }
  }

  function getItemByBody(body) {
    return G.items.find(it => it.body === body);
  }

  // ============================================================
  // Drop System
  // ============================================================
  function dropJellyfish() {
    if (G.paused) return;
    if (!G.canDrop) return;
    if (G.phase !== 'playing') return;
    if (G.dropLevel === null) return;

    const level = G.dropLevel;
    const C = CONFIG.CONTAINER;
    const x = G.clipX;
    const y = CONFIG.ANIM.dropStartY;

    const body = createJellyfishBody(x, y, level);
    const item = addJellyfishItem(body, level);

    Composite.add(G.engine.world, body);
    item.bodyInWorld = true;

    item.pendingDropImpact = true;
    playSound('click');

    // Clear clip — 轮空期间夹子上无水母
    G.dropLevel = null;
    G.canDrop = false;

    // After 1s cooldown, next-in-line moves to clip and pick what follows
    const readyDrop = () => {
      if (G.paused) { G.dropCooldownTimer = setTimeout(readyDrop,100); return; }
      G.dropCooldownTimer = null;
      G.dropLevel = G.nextLevel;
      G.clipAppearStart = performance.now();
      G.nextLevel = pickNextLevel();
      G.nextAppearStart = performance.now();
      G.canDrop = true;
    };
    G.dropCooldownTimer = setTimeout(readyDrop, 1000);
  }

  // ============================================================
  // Debug: spawn random jellyfish (press C key)
  // ============================================================
  function spawnRandomJellyfish(count) {
    if (G.phase !== 'playing') return;
    for (let i = 0; i < count; i++) {
      const level = pickNextLevel();
      const C = CONFIG.CONTAINER;
      const x = C.left + 30 + Math.random() * (C.right - C.left - 60);
      const y = C.top + 20 + Math.random() * 120;
      const body = createJellyfishBody(x, y, level);
      const item = addJellyfishItem(body, level);
      Composite.add(G.engine.world, body);
      item.bodyInWorld = true;
    }
  }

  // ============================================================
  // Merge System
  // ============================================================
  function triggerMerge(bodyA, bodyB) {
    const itemA = getItemByBody(bodyA);
    const itemB = getItemByBody(bodyB);
    if (!itemA || !itemB) return;
    if (itemA.isMerging || itemB.isMerging) return;
    if (itemA.level >= 11) return;  // max level, can't merge

    const level = itemA.level;
    const newLevel = level + 1;
    const midX = (bodyA.position.x + bodyB.position.x) / 2;
    const midY = (bodyA.position.y + bodyB.position.y) / 2;

    // Mark as merging
    itemA.isMerging = true;
    itemB.isMerging = true;

    // Removing support can destabilise the entire connected stack. Wake it so
    // sleeping bodies fall into the gap instead of remaining suspended.
    for (const item of G.items) {
      if (item.bodyInWorld && !item.isMerging && item.body.isSleeping) {
        Sleeping.set(item.body, false);
      }
    }
    for (const item of [itemA, itemB]) {
      item.bodyInWorld = false;
      item.previousPose = {
        x: item.body.position.x, y: item.body.position.y, angle: item.body.angle,
      };
    }

    // Remove physics bodies from world (keep items for ghost rendering)
    Composite.remove(G.engine.world, bodyA);
    Composite.remove(G.engine.world, bodyB);

    // Add score
    const scoreDef = CONFIG.JELLYFISH[newLevel - 1];
    G.score += scoreDef.score;
    G.totalScore += scoreDef.score;

    // Play merge sound
    if (scoreDef.audio) {
      playSound(scoreDef.audio);
    }

    // Create merge animation
    G.merges.push({
      phase: 'shrink',
      progress: 0,
      itemA,
      itemB,
      midX,
      midY,
      newLevel,
      newItem: null,
    });
  }

  function updateMergeAnimations(dt) {
    const duration = CONFIG.ANIM.mergeDuration; // ms

    for (let i = G.merges.length - 1; i >= 0; i--) {
      const m = G.merges[i];
      m.progress += dt;

      const t = Math.min(m.progress / duration, 1);
      const s = 1 - easeInOutCubic(t);
      m.itemA.visualScale = s;
      m.itemB.visualScale = s;

      if (t >= 1) {
        // Shrink complete — discard ghost items, create new jellyfish at full size
        removeJellyfishItem(m.itemA.body);
        removeJellyfishItem(m.itemB.body);

        const newBody = createJellyfishBody(m.midX, m.midY, m.newLevel);
        const newItem = addJellyfishItem(newBody, m.newLevel);
        newItem.visualScale = 1;
        newItem.isMerging = false;
        Composite.add(G.engine.world, newBody);
        newItem.bodyInWorld = true;

        G.merges.splice(i, 1);
      }
    }
  }

  // ============================================================
  // Collision Detection
  // ============================================================
  function tryMergePair(ba, bb) {
    if (ba === bb) return;
    if (!ba.jellyfishLevel || !bb.jellyfishLevel) return;
    if (ba.jellyfishLevel !== bb.jellyfishLevel) return;
    if (ba.jellyfishLevel >= 11) return;

    const ia = getItemByBody(ba);
    const ib = getItemByBody(bb);
    if (!ia || !ib) return;
    if (ia.isMerging || ib.isMerging) return;

    triggerMerge(ba, bb);
  }

  function setupCollisionHandler() {
    // Helper: sum of item IDs for a collision pair (lower = older)
    function pairAgeSum(pair) {
      const ia = getItemByBody(pair.bodyA.parent);
      const ib = getItemByBody(pair.bodyB.parent);
      return (ia ? ia.id : Infinity) + (ib ? ib.id : Infinity);
    }

    // Primary: collisionStart fires for new overlaps
    Events.on(G.engine, 'collisionStart', (event) => {
      if (G.phase !== 'playing') return;
      // Sort: older items merge first when multiple pairs exist
      const sorted = [...event.pairs].sort((a, b) => pairAgeSum(a) - pairAgeSum(b));
      for (const pair of sorted) {
        tryMergePair(pair.bodyA.parent, pair.bodyB.parent);
      }
      // Resolve all merges first so a drop touching multiple neighbours does
      // not get both a landing sound and a merge sound in the same step.
      const impacts = new Set();
      for (const pair of sorted) {
        const a = getItemByBody(pair.bodyA.parent);
        const b = getItemByBody(pair.bodyB.parent);
        if ((a && a.isMerging) || (b && b.isMerging)) continue;
        if (a && a.pendingDropImpact && (b || pair.bodyB.parent.label === 'floor')) impacts.add(a);
        if (b && b.pendingDropImpact && (a || pair.bodyA.parent.label === 'floor')) impacts.add(b);
      }
      for (const item of impacts) {
        item.pendingDropImpact = false;
        playSound('form1');
      }
    });

    // Backup: collisionActive fires every frame for sustained overlaps
    Events.on(G.engine, 'collisionActive', (event) => {
      if (G.phase !== 'playing') return;
      const sorted = [...event.pairs].sort((a, b) => pairAgeSum(a) - pairAgeSum(b));
      for (const pair of sorted) {
        tryMergePair(pair.bodyA.parent, pair.bodyB.parent);
      }
    });
  }

  // ============================================================
  // Periodic Merge Scan (safety net for sleeping pairs)
  // ============================================================
  function scanForMerges() {
    const active = G.items.filter(it => !it.isMerging && it.level < 11 && it.bodyInWorld);
    for (let i = 0; i < active.length; i++) {
      for (let j = i + 1; j < active.length; j++) {
        const a = active[i], b = active[j];
        if (a.level !== b.level) continue;
        const dx = a.body.position.x - b.body.position.x;
        const dy = a.body.position.y - b.body.position.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        // Use 85% of combined half-size as contact threshold
        const contactDist = (Math.max(a.w, a.h) + Math.max(b.w, b.h)) / 2 * 0.85;
        if (dist < contactDist) {
          tryMergePair(a.body, b.body);
        }
      }
    }
  }

  // ============================================================
  // Game Over Detection
  // ============================================================
  function checkGameOver() {
    if (G.phase !== 'playing') return;
    if (G.merges.length > 0) return;  // Wait during merges

    const C = CONFIG.CONTAINER;
    const GRACE_MS = 1500; // Ignore recently created items (give them time to settle)
    const now = performance.now();
    let overflowing = false;

    for (const item of G.items) {
      if (item.isMerging) continue;
      if (!item.bodyInWorld) continue;
      // Grace period: newly dropped/merged jellyfish need time to fall into container
      if (now - item.spawnTime < GRACE_MS) continue;
      // Check if jellyfish's top edge is above the container top
      if (item.body.bounds.min.y < C.top) {
        overflowing = true;
        break;
      }
    }

    if (overflowing) {
      if (G.overflowStart === null) {
        G.overflowStart = now;
      } else if (now - G.overflowStart >= CONFIG.ANIM.overflowTime) {
        G.phase = 'gameover';
        playSound('start');
      }
    } else {
      G.overflowStart = null;
    }
  }

  // ============================================================
  // Audio
  // ============================================================
  let bgm = null;
  let bgmPlayPending = false;
  const audioSettings = { musicVolume: CONFIG.AUDIO.backgroundVolume, effectsVolume: 1 };
  const activeSounds = new Map();
  try {
    const saved = JSON.parse(localStorage.getItem('jellyfish.audioSettings') || '{}');
    for (const key of ['musicVolume', 'effectsVolume']) {
      if (typeof saved[key] === 'number' && Number.isFinite(saved[key])) audioSettings[key] = clamp(saved[key], 0, 1);
    }
  } catch (e) {}

  function playSound(key) {
    const audio = G.assets.audio[key];
    if (!audio) return;
    try {
      const clone = audio.cloneNode();
      const gain = key === 'countdown' ? 0.55 : key === 'goWhistle' ? 0.65 : 1.0;
      clone.volume = gain * audioSettings.effectsVolume;
      activeSounds.set(clone, gain);
      if (clone.addEventListener) clone.addEventListener('ended', () => activeSounds.delete(clone), { once: true });
      clone.play().catch(() => { activeSounds.delete(clone); });
    } catch (e) {
      // Ignore autoplay errors
    }
  }

  function startBackgroundMusic() {
    if (G.paused) return;
    try {
      if (!bgm) {
        bgm = new Audio(CONFIG.AUDIO.background);
        bgm.loop = true;
        bgm.preload = 'auto';
        bgm.volume = audioSettings.musicVolume;
      }
      if (!bgm.paused || bgmPlayPending) return;
      bgmPlayPending = true;
      const attempt = bgm.play();
      if (attempt) attempt.catch(() => {}).finally(() => { bgmPlayPending = false; });
      else bgmPlayPending = false;
    } catch (e) { bgmPlayPending = false; }
  }

  function setupSettings() {
    ChalkUI.install();
    const toggle = document.getElementById('settingsToggle');
    const panel = document.getElementById('settingsPanel');
    const setOpen = open => { panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); };
    toggle.addEventListener('click', () => setOpen(panel.hidden));
    document.addEventListener('pointerdown', event => {
      if (!event.target.closest('.settings')) setOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !panel.hidden) { setOpen(false); toggle.focus(); }
    });
    for (const [id, key] of [['musicVolume', 'musicVolume'], ['effectsVolume', 'effectsVolume']]) {
      const slider = document.getElementById(id);
      const output = document.getElementById(id + 'Value');
      slider.value = audioSettings[key];
      const update = () => {
        output.textContent = Math.round(audioSettings[key] * 100) + '%';
        slider.parentElement.style.setProperty('--value', audioSettings[key]);
      };
      update();
      slider.addEventListener('input', () => {
        audioSettings[key] = clamp(Number(slider.value), 0, 1);
        if (bgm) bgm.volume = audioSettings.musicVolume;
        for (const [sound, gain] of activeSounds) sound.volume = gain * audioSettings.effectsVolume;
        update();
        try { localStorage.setItem('jellyfish.audioSettings', JSON.stringify(audioSettings)); } catch (e) {}
      });
    }
    document.getElementById('restartButton').addEventListener('click', () => {
      if (!G.engine || !G.assets) return;
      if (!window.JellyfishSession.newGame()) return;
      restartGame(); startGame(); setOpen(false);
    });
  }

  // ============================================================
  // Input Handling
  // ============================================================
  function setupInput() {
    const canvas = G.canvas;

    function getGamePos(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (clientX - rect.left) * (CONFIG.GAME_WIDTH / rect.width),
        y: (clientY - rect.top) * (CONFIG.GAME_HEIGHT / rect.height),
      };
    }

    function onDown(cx, cy) {
      if (G.paused) return;
      const pos = getGamePos(cx, cy);

      if (G.phase === 'title') {
        startGame();
        return;
      }

      if (G.phase === 'gameover') {
        restartGame();
        return;
      }

      if (G.phase === 'playing') {
        G.isDragging = true;
        G.clipX = clamp(pos.x, CONFIG.CLIP.minX, CONFIG.CLIP.maxX);
      }
    }

    function onMove(cx, cy) {
      if (!G.isDragging) return;
      const pos = getGamePos(cx, cy);
      G.clipX = clamp(pos.x, CONFIG.CLIP.minX, CONFIG.CLIP.maxX);
    }

    function onUp() {
      if (G.isDragging) {
        G.isDragging = false;
        dropJellyfish();
      }
    }

    // Mouse
    canvas.addEventListener('mousedown', (e) => onDown(e.clientX, e.clientY));
    canvas.addEventListener('mousemove', (e) => onMove(e.clientX, e.clientY));
    canvas.addEventListener('mouseup', (e) => onUp());
    canvas.addEventListener('mouseleave', (e) => {
      if (G.isDragging) {
        G.isDragging = false;
        dropJellyfish();
      }
    });

    // Touch
    canvas.addEventListener('touchstart', (e) => {
      e.preventDefault();
      const t = e.touches[0];
      onDown(t.clientX, t.clientY);
    }, { passive: false });
    canvas.addEventListener('touchmove', (e) => {
      e.preventDefault();
      const t = e.touches[0];
      onMove(t.clientX, t.clientY);
    }, { passive: false });
    canvas.addEventListener('touchend', (e) => {
      e.preventDefault();
      onUp();
    }, { passive: false });

    // Keyboard — debug: C to spawn 10 random jellyfish
    document.addEventListener('keydown', (e) => {
      if (G.paused || e.target.closest('.session-ui')) return;
      if (e.target.closest && e.target.closest('.settings')) return;
      if (['ArrowLeft', 'ArrowRight', 'ArrowDown', 'Enter'].includes(e.key)) {
        e.preventDefault();
        if (e.key === 'ArrowLeft') G.keys.left = true;
        if (e.key === 'ArrowRight') G.keys.right = true;
        if (!e.repeat && (e.key === 'Enter' || e.key === 'ArrowDown')) {
          if (G.phase === 'title') startGame();
          else if (G.phase === 'gameover') restartGame();
          else dropJellyfish();
        }
      }
      if ((e.key === 'c' || e.key === 'C') && G.phase === 'playing') {
        spawnRandomJellyfish(10);
      }
    });
    document.addEventListener('keyup', (e) => {
      if (e.key === 'ArrowLeft') G.keys.left = false;
      if (e.key === 'ArrowRight') G.keys.right = false;
    });
    window.addEventListener('blur', () => {
      G.keys.left = G.keys.right = false;
      G.isDragging = false;
    });
  }

  // ============================================================
  // Game State Transitions
  // ============================================================
  function startGame() {
    G.phase = 'countdown';
    G.countdownStart = performance.now();
    G.countdownEnd = G.countdownStart + CONFIG.ANIM.countdownStepDuration * 3
      + CONFIG.ANIM.countdownGoDuration;
    G.countdownCue = 0;
    playSound('countdown');
  }

  function beginPlaying() {
    G.bubbleTransition = null;
    G.phase = 'playing';
    G.score = 0;
    G.items = [];
    G.merges = [];
    G.overflowStart = null;
    G.dropLevel = pickNextLevel();
    G.nextLevel = pickNextLevel();
    G.clipAppearStart = performance.now();
    G.nextAppearStart = performance.now();
    G.canDrop = true;
    G.runId = window.JellyfishSession.beginRun();

  }

  function restartGame() {
    G.paused = false;
    for (const sound of activeSounds.keys()) sound.pause();
    activeSounds.clear();
    if (G.dropCooldownTimer !== null) clearTimeout(G.dropCooldownTimer);
    G.dropCooldownTimer = null;
    G.isDragging = false;
    G.keys.left = G.keys.right = false;
    G.bubbleTransition = null;
    G.physicsAccumulator = 0;
    // Clean up existing physics
    for (const item of G.items) {
      Composite.remove(G.engine.world, item.body);
    }
    G.items = [];
    G.merges = [];
    G.overflowStart = null;
    G.canDrop = true;
    G.score = 0;
    G.totalScore = 0;
    G.clipX = (CONFIG.CLIP.minX + CONFIG.CLIP.maxX) / 2;
    G.dropLevel = pickNextLevel();
    G.nextLevel = pickNextLevel();
    G.overflowStart = null;
    G.clipAppearStart = -1;
    G.nextAppearStart = -1;

    G.phase = 'title';
  }

  // ============================================================
  // Rendering
  // ============================================================
  function render(timestamp) {
    const ctx = G.ctx;
    const W = CONFIG.GAME_WIDTH;
    const H = CONFIG.GAME_HEIGHT;

    // If assets not loaded yet, just show loading
    if (!G.assets) {
      drawLoading(ctx, W, H);
      return;
    }

    const as = G.assets.images;

    ctx.clearRect(0, 0, W, H);

    if (G.phase === 'title' || G.phase === 'countdown') {
      OpeningScene.draw(ctx, G.assets, timestamp);
      if (G.phase === 'title') drawTitle(ctx, W, H);
      else OpeningScene.drawCountdown(ctx, timestamp - G.countdownStart);
      return;
    }
    if (G.phase === 'transition' && G.bubbleTransition) {
      const elapsed = timestamp - G.bubbleTransition.start;
      const t = clamp((elapsed - 150) / 1000, 0, 1);
      const reveal = .18 * t + .82 * t * t;
      OpeningScene.drawReveal(ctx, G.assets, timestamp, reveal, t);
      BubbleTransition.draw(ctx, G.bubbleTransition, timestamp);
      return;
    }

    // --- Background ---
    if (as.background) {
      ctx.drawImage(as.background, 0, 0, W, H);
    } else {
      ctx.fillStyle = '#0a1628';
      ctx.fillRect(0, 0, W, H);
    }

    // --- Warning overlay (pulsing red border when overflow detected) ---
    if (G.phase === 'playing' && G.overflowStart !== null && as.warning) {
      const elapsed = timestamp - G.overflowStart;
      const pulse = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(elapsed * 0.006));
      ctx.save();
      ctx.globalAlpha = pulse;
      ctx.drawImage(as.warning, 0, 0, W, H);
      ctx.restore();
    }

    drawBackgroundLabels(ctx);

    if (G.phase === 'loading') {
      drawLoading(ctx, W, H);
      return;
    }

    // --- Jellyfish (depth-sorted, non-merging only) ---
    const activeItems = G.items.filter(it => !it.isMerging);
    activeItems.sort((a, b) => a.body.position.y - b.body.position.y);

    for (const item of activeItems) {
      drawJellyfish(ctx, item);
    }

    // --- Merge animations (shrinking ghosts) ---
    for (const m of G.merges) {
      if (m.itemA.body) drawJellyfish(ctx, m.itemA);
      if (m.itemB.body) drawJellyfish(ctx, m.itemB);
    }

    // --- Clip ---
    if (G.phase === 'playing' || G.phase === 'countdown' || G.phase === 'transition') {
      drawClip(ctx);
    }

    // --- Aim line (visible during drag only) ---
    if (G.phase === 'playing' && G.isDragging) {
      drawAimLine(ctx);
    }

    // --- Drop preview ---
    if (G.phase === 'playing' && G.dropLevel !== null) {
      drawDropPreview(ctx);
    }

    // --- Next jellyfish preview (static position) ---
    if (G.phase === 'playing') {
      drawNextPreview(ctx);
    }

    // --- Score ---
    if (G.phase === 'playing') {
      drawScore(ctx);
    }

    // --- Overlay states ---
    if (G.phase === 'title') {
      drawTitle(ctx, W, H);
    } else if (G.phase === 'countdown') {
      drawCountdown(ctx, W, H, timestamp);
    } else if (G.phase === 'gameover') {
      drawGameOver(ctx, W, H);
    }
    if (G.phase === 'transition' && G.bubbleTransition) {
      BubbleTransition.draw(ctx, G.bubbleTransition, timestamp);
    }
  }

  // ============================================================
  // Drawing Utilities
  // ============================================================
  function drawJellyfish(ctx, item) {
    // Skip rendering for extremely tiny scales (causes dark sub-pixel artifacts)
    if (item.visualScale < 0.02) return;

    const body = item.body;
    if (!body) return;
    // Interpolate completed physics steps for smooth rendering at any refresh rate.
    const alpha = G.phase === 'playing' && !item.isMerging
      ? G.physicsAccumulator / CONFIG.PHYSICS.fixedDelta : 1;
    const previous = item.previousPose;
    const x = lerp(previous.x, body.position.x, alpha);
    const y = lerp(previous.y, body.position.y, alpha);
    const angle = lerp(previous.angle, body.angle, alpha);
    const s = item.visualScale;

    ctx.save();

    // Reset canvas state to prevent cross-contamination
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';

    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.scale(s, s);

    // Draw sprite
    if (item.sprite) {
      drawInternalBreathing(ctx, item);
    } else {
      // Fallback: colored circle/ellipse
      ctx.fillStyle = `hsl(${(item.level * 30) % 360}, 70%, 60%)`;
      ctx.beginPath();
      if (item.w === item.h) {
        ctx.arc(0, 0, item.w / 2, 0, Math.PI * 2);
      } else {
        ctx.ellipse(0, 0, item.w / 2, item.h / 2, 0, 0, Math.PI * 2);
      }
      ctx.fill();
    }

    // Glass overlay
    drawGlassEffect(ctx, item.w, item.h);

    ctx.restore();
  }

  function drawGlassEffect(ctx, w, h) {
    // Removed — jellyfish use original asset sprites without extra effects
  }

  // Anatomy-aware animation renderer is implemented in js/jellyfish-animation.js.
  function drawInternalBreathing(ctx, item) {
    JellyfishAnimation.draw(ctx, item, CONFIG.ANIM.breathing[item.level - 1]);
  }

  function drawClip(ctx) {
    const as = G.assets.images;
    if (!as.clip) return;

    const x = G.clipX;
    const cw = as.clip.width;
    const ch = as.clip.height;

    // Draw clip sprite (anchor: center-top)
    ctx.drawImage(as.clip, x - cw / 2, 0, cw, ch);
  }

  function drawDropPreview(ctx) {
    const level = G.dropLevel;
    if (level === null) return;
    const def = CONFIG.JELLYFISH[level - 1];
    const sprite = G.assets.images[`fish${level}`];
    const x = G.clipX;
    const previewY = CONFIG.ANIM.dropStartY;

    // Appear animation: scale 0→1 over 0.5s
    let scale = 1;
    if (G.clipAppearStart >= 0) {
      const elapsed = performance.now() - G.clipAppearStart;
      const t = Math.min(elapsed / 500, 1);
      scale = easeInOutCubic(t);
      if (t >= 1) G.clipAppearStart = -1;
    }

    ctx.save();
    ctx.globalAlpha = G.ghostAlpha;
    ctx.translate(x, previewY);
    ctx.scale(scale, scale);

    if (sprite) {
      drawInternalBreathing(ctx, {
        level, sprite, w: def.width, h: def.height, breathPhase: level * 1.7,
      });
    }

    // Glass effect on preview
    const rx = def.width / 2;
    const ry = def.height / 2;
    const grad = ctx.createRadialGradient(-rx * 0.3, -ry * 0.3, 0, 0, 0, Math.max(rx, ry));
    grad.addColorStop(0, 'rgba(255,255,255,0.2)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.beginPath();
    ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.restore();
  }

  function drawAimLine(ctx) {
    const as = G.assets.images;
    if (!as.line) return;
    const lw = as.line.width;
    const lh = as.line.height;
    const lineH = Math.min(lh, CONFIG.CONTAINER.bottom + 20);
    ctx.save();
    ctx.globalAlpha = 0.35;
    ctx.drawImage(as.line, G.clipX - lw / 2, 0, lw, lineH);
    ctx.restore();
  }

  // ============================================================
  // UI Rendering
  // ============================================================
  function removeBackgroundGlyphs(image) {
    const canvas = document.createElement('canvas');
    canvas.width = CONFIG.GAME_WIDTH;
    canvas.height = CONFIG.GAME_HEIGHT;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    for (const [center, width] of [[676, 250], [1896.5, 230], [2410, 280]]) {
      const x = Math.round(center - width / 2), y = 55, height = 70;
      const pixels = ctx.getImageData(x, y, width, height);
      const data = pixels.data;
      const mask = new Uint8Array(width * height);
      for (let row = 2; row < height - 2; row++) {
        for (let col = 2; col < width - 2; col++) {
          const index = (row * width + col) * 4;
          if (data[index] > 80 && data[index + 1] > 110 && data[index + 2] > 135) {
            for (let dy = -2; dy <= 2; dy++) {
              for (let dx = -2; dx <= 2; dx++) mask[(row + dy) * width + col + dx] = 1;
            }
          }
        }
      }
      // Diffuse only glyph pixels from neighbouring background. All unmasked
      // pixels remain byte-for-byte identical: no stretched rectangular strip.
      for (let row = 1; row < height - 1; row++) {
        for (let col = 1; col < width - 1; col++) {
          const p = row * width + col;
          if (!mask[p]) continue;
          for (let channel = 0; channel < 3; channel++) data[p * 4 + channel] = data[col * 4 + channel];
        }
      }
      for (let pass = 0; pass < 80; pass++) {
        for (let row = 1; row < height - 1; row++) {
          for (let col = 1; col < width - 1; col++) {
            const p = row * width + col;
            if (!mask[p]) continue;
            for (let channel = 0; channel < 3; channel++) {
              data[p * 4 + channel] = (data[(p - 1) * 4 + channel] + data[(p + 1) * 4 + channel]
                + data[(p - width) * 4 + channel] + data[(p + width) * 4 + channel]) / 4;
            }
          }
        }
      }
      ctx.putImageData(pixels, x, y);
    }
    return canvas;
  }

  function drawBackgroundLabels(ctx) {
    const background = G.assets.images.background;
    if (!background) return;
    ctx.save();
    ctx.font = `54px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = '#b9e2f4';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // The original glyphs are removed at load time, without rectangular plates.
    for (const [x, width, label] of [
      [676, 250, '我的得分'], [1896.5, 230, '下一个'], [2410, 280, '水母图鉴'],
    ]) {
      ctx.fillText(label, x, 90);
    }
    ctx.restore();
  }

  function drawScore(ctx) {
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `80px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0,0,0,0.5)';
    ctx.shadowBlur = 3;
    ctx.fillText(`${G.score}`, 676, 251);
    ctx.restore();
  }

  function drawNextPreview(ctx) {
    const level = G.nextLevel;
    const def = CONFIG.JELLYFISH[level - 1];
    const sprite = G.assets.images[`fish${level}`];
    const px = 1896.5;
    const py = 246;

    // Appear animation: scale 0→1 over 0.5s
    let scale = 1;
    if (G.nextAppearStart >= 0) {
      const elapsed = performance.now() - G.nextAppearStart;
      const t = Math.min(elapsed / 500, 1);
      scale = easeInOutCubic(t);
      if (t >= 1) G.nextAppearStart = -1;
    }

    ctx.save();
    ctx.translate(px, py);
    ctx.scale(scale, scale);

    if (sprite) {
      drawInternalBreathing(ctx, {
        level, sprite, w: def.width, h: def.height, breathPhase: level * 2.3,
      });
      // Subtle glass effect on the preview
      const rx = def.width / 2;
      const ry = def.height / 2;
      const grad = ctx.createRadialGradient(-rx * 0.3, -ry * 0.3, 0, 0, 0, Math.max(rx, ry));
      grad.addColorStop(0, 'rgba(255,255,255,0.15)');
      grad.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.beginPath();
      ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
    }

    ctx.restore();
  }

  function drawTitle(ctx, W, H) {
    ctx.save();

    // Dark overlay
    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    ctx.fillRect(0, 0, W, H);

    // Title
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `72px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0, 150, 255, 0.6)';
    ctx.shadowBlur = 20;
    ctx.fillText('合成大水母', W * .51, H * .43 - 60);

    ctx.shadowBlur = 0;
    ctx.font = `24px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.fillText('点击任意位置开始游戏', W * .51, H * .43 + 32);

    ctx.font = `16px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.fillText('鼠标拖动瞄准，松开投放 · ← → 移动 · Enter / ↓ 投放', W * .51, H * .43 + 80);

    ctx.restore();
  }

  function drawCountdown(ctx, W, H, timestamp) {
    const remaining = Math.max(0, (G.countdownEnd - timestamp) / 1000);
    const display = Math.ceil(remaining);

    ctx.save();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.fillRect(0, 0, W, H);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `120px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0, 150, 255, 0.5)';
    ctx.shadowBlur = 30;
    ctx.fillText(`${display}`, W / 2, H / 2);

    ctx.shadowBlur = 0;
    ctx.font = `28px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
    ctx.fillText('准备开始！', W / 2, H / 2 + 100);

    ctx.restore();
  }

  function drawGameOver(ctx, W, H) {
    ctx.save();
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    ctx.fillRect(0, 0, W, H);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    ctx.font = `64px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = '#ff6b6b';
    ctx.shadowColor = 'rgba(255, 0, 0, 0.4)';
    ctx.shadowBlur = 15;
    ctx.fillText('游戏结束', W / 2, H / 2 - 80);

    ctx.shadowBlur = 0;
    ctx.font = `40px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = '#ffffff';
    ctx.fillText(`得分: ${G.score}`, W / 2, H / 2 + 10);

    ctx.font = `22px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.fillText('点击任意位置重新开始', W / 2, H / 2 + 80);

    ctx.restore();
  }

  function drawLoading(ctx, W, H) {
    const progress = Loader.getProgress();

    ctx.save();
    ctx.fillStyle = '#0a1628';
    ctx.fillRect(0, 0, W, H);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    ctx.font = `28px ${CONFIG.FONT_FAMILY}`;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
    ctx.fillText('加载中...', W / 2, H / 2 - 40);

    // Progress bar
    const barW = 400, barH = 24;
    const bx = W / 2 - barW / 2, by = H / 2;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 2;
    ctx.strokeRect(bx, by, barW, barH);
    ctx.fillStyle = 'rgba(100, 200, 255, 0.7)';
    ctx.fillRect(bx + 2, by + 2, (barW - 4) * Math.min(progress, 1), barH - 4);

    ctx.restore();
  }

  // ============================================================
  // Main Loop
  // ============================================================
  function loop(timestamp) {
    if (G.paused) {
      G.lastTime = 0;
      setTimeout(() => requestAnimationFrame(loop), 120);
      return;
    }
    const dt = G.lastTime ? Math.min(timestamp - G.lastTime, 50) : 16.67;
    G.lastTime = timestamp;

    // --- Phase transitions ---
    if (G.phase === 'countdown' && timestamp < G.countdownEnd) {
      const cue = Math.min(3, Math.floor(Math.max(0, timestamp - G.countdownStart) / CONFIG.ANIM.countdownStepDuration));
      if (cue !== G.countdownCue) {
        G.countdownCue = cue;
        playSound(cue === 3 ? 'goWhistle' : 'countdown');
      }
    }
    if (G.phase === 'countdown' && timestamp >= G.countdownEnd) {
      G.phase = 'transition';
      G.keys.left = G.keys.right = false;
      G.bubbleTransition = BubbleTransition.create(timestamp, CONFIG.GAME_WIDTH,
        CONFIG.GAME_HEIGHT, CONFIG.ANIM.bubbleTransitionDuration, CONFIG.ANIM.bubbleCount,
        G.assets.images.bubble);
      playSound('start');
    }
    if (G.phase === 'transition'
      && timestamp - G.bubbleTransition.start >= G.bubbleTransition.duration) {
      beginPlaying();
    }

    // --- Physics ---
    if (G.phase === 'playing') {
      const direction = Number(G.keys.right) - Number(G.keys.left);
      if (direction) G.clipX = clamp(G.clipX + direction * CONFIG.CLIP.keyboardSpeed * dt / 1000,
        CONFIG.CLIP.minX, CONFIG.CLIP.maxX);
      const step = CONFIG.PHYSICS.fixedDelta;
      G.physicsAccumulator = Math.min(
        G.physicsAccumulator + dt, step * CONFIG.PHYSICS.maxSubSteps
      );
      while (G.physicsAccumulator >= step) {
        for (const item of G.items) {
          if (!item.bodyInWorld || item.isMerging) continue;
          item.previousPose.x = item.body.position.x;
          item.previousPose.y = item.body.position.y;
          item.previousPose.angle = item.body.angle;
        }
        Engine.update(G.engine, step);
        updateMergeAnimations(step);
        G.physicsAccumulator -= step;
      }

      // Periodic merge safety net — catches pairs missed by collision events
      if (timestamp - G.lastMergeScan > 2000) {
        G.lastMergeScan = timestamp;
        scanForMerges();
      }

      checkGameOver();
      if (G.phase === 'gameover') window.JellyfishSession.completeRun();
    } else {
      G.physicsAccumulator = 0;
    }

    // --- Render ---
    render(timestamp);

    requestAnimationFrame(loop);
  }

  // ============================================================
  // Resize
  // ============================================================
  function resizeCanvas() {
    const canvas = G.canvas;
    const scale = Math.min(
      window.innerWidth / CONFIG.GAME_WIDTH,
      window.innerHeight / CONFIG.GAME_HEIGHT
    );
    const w = CONFIG.GAME_WIDTH * scale;
    const h = CONFIG.GAME_HEIGHT * scale;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
  }

  // ============================================================
  // Bootstrap
  // ============================================================
  async function init() {
    startBackgroundMusic();
    // Browsers may block sound until the first user gesture. Retry without
    // recreating the track, so it continues across title, countdown and games.
    window.addEventListener('pointerdown', startBackgroundMusic, { capture: true });
    window.addEventListener('keydown', startBackgroundMusic, { capture: true });
    const canvas = document.getElementById('gameCanvas');
    canvas.width = CONFIG.GAME_WIDTH;
    canvas.height = CONFIG.GAME_HEIGHT;
    G.canvas = canvas;
    G.ctx = canvas.getContext('2d');

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Setup input
    setupInput();
    setupSettings();

    // Start render loop immediately (shows loading screen)
    requestAnimationFrame(loop);

    // Load assets (async)
    const fontReady = document.fonts.load('54px "JellyfishPOP"', '合成大水母我的得分下一个水母图鉴0123456789')
      .catch(() => console.warn('华康POP1体W5未安装：请添加 assets/fonts/DFPOP1-W5.ttf'));
    const countdownFontReady = document.fonts.load('180px "JellyfishCountdown"', '321GO!')
      .catch(() => console.warn('倒计时字体加载失败：汉仪第五人格体.ttf'));
    const [assets] = await Promise.all([Loader.loadAll(), fontReady, countdownFontReady]);
    G.assets = assets;
    for (const key of ['background', 'warning']) {
      if (G.assets.images[key]) G.assets.images[key] = removeBackgroundGlyphs(G.assets.images[key]);
    }

    // Init physics
    initPhysics();
    setupCollisionHandler();

    // Show title
    G.phase = 'title';
    G.clipX = (CONFIG.CLIP.minX + CONFIG.CLIP.maxX) / 2;
    G.dropLevel = pickNextLevel();
    G.nextLevel = pickNextLevel();
    G.clipAppearStart = -1;
    G.nextAppearStart = -1;
    window.JellyfishSession.install({
      state: G,
      pause() {
        if (G.phase !== 'playing' && G.phase !== 'gameover') return false;
        if (G.paused) return true;
        G.paused = true; G.pauseTime = performance.now();
        G.isDragging = false; G.keys.left = G.keys.right = false;
        if (bgm) bgm.pause();
        for (const sound of activeSounds.keys()) sound.pause();
        return true;
      },
      resume() {
        if (G.overflowStart !== null) G.overflowStart += performance.now() - G.pauseTime;
        G.paused = false; G.lastTime = 0; startBackgroundMusic();
      },
      snapshot() {
        const fish = G.items.filter(i => !i.isMerging).map(i => ({
          level: i.level, x: i.body.position.x, y: i.body.position.y,
          angle: i.body.angle, vx: i.body.velocity.x, vy: i.body.velocity.y,
          av: i.body.angularVelocity, sleeping: i.body.isSleeping
        }));
        // A merge has already awarded its points: save its resulting fish,
        // rather than ghost parents that would award the same points again.
        for (const m of G.merges) fish.push({level:m.newLevel,x:m.midX,y:m.midY,angle:0,vx:0,vy:0,av:0,sleeping:false});
        return {version:1,runId:G.runId,score:G.score,totalScore:G.totalScore,
          clipX:G.clipX,dropLevel:G.dropLevel,nextLevel:G.nextLevel,fish};
      },
      restore(s) {
        restartGame(); G.phase = 'playing'; G.runId = s.runId;
        G.score = s.score; G.totalScore = s.totalScore;
        G.clipX = clamp(s.clipX,CONFIG.CLIP.minX,CONFIG.CLIP.maxX);
        G.dropLevel = s.dropLevel === null ? s.nextLevel : s.dropLevel;
        G.nextLevel = s.dropLevel === null ? pickNextLevel() : s.nextLevel;
        for (const f of s.fish) {
          const body = createJellyfishBody(f.x,f.y,f.level);
          Matter.Body.setAngle(body,f.angle); Matter.Body.setVelocity(body,{x:f.vx,y:f.vy});
          Matter.Body.setAngularVelocity(body,f.av);
          const item = addJellyfishItem(body,f.level);
          item.previousPose = {x:body.position.x,y:body.position.y,angle:body.angle};
          item.spawnTime = -10000; item.bodyInWorld = true;
          Composite.add(G.engine.world,body); Sleeping.set(body,!!f.sleeping);
        }
        G.clipAppearStart = G.nextAppearStart = -1;
        G.lastTime = 0; G.physicsAccumulator = 0;
      },
      restart() { restartGame(); startGame(); }
    });
  }

  // --- Start ---
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
