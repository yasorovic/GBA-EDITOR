import { load } from "./vendor/mgba.sdk.js";
import { openCartridgeSave } from "./save.js";
import { loadShader, ShaderScreen } from "./shaders.js";

const canvas = document.querySelector("#screen");
const curtain = document.querySelector("#curtain");
const status = document.querySelector("#status");
const romInput = document.querySelector("#rom-file");
const playButton = document.querySelector("#play");
const bundledRom = playButton.dataset.rom;
romInput.closest("label").hidden = Boolean(bundledRom);
const muteButton = document.querySelector("#mute");
const fullscreenButton = document.querySelector("#fullscreen");
const mobilePreviewButton = document.querySelector("#mobile-preview");
const prototype = document.querySelector(".web-prototype");
const compatibility = document.querySelector("#compatibility");
const touchLayout = document.querySelector("#touch-layout");
const previewOrientation = document.querySelector("#preview-orientation");
const player = document.querySelector(".player");
const frameStyle = document.querySelector("#frame-style");
const framePicker = document.querySelector("#frame-picker");
const frameFile = document.querySelector("#frame-file");
const frameStatus = document.querySelector("#frame-status");
const touchPointer = matchMedia("(pointer: coarse)");
const isItch = /(^|\.)itch\.(io|zone)$/.test(location.hostname);
const isFirefoxAndroid = /\bAndroid\b.*\bFirefox\//.test(navigator.userAgent);
const landscapeViewport = matchMedia("(orientation: landscape)");
const gamepadStatus = document.querySelector("#gamepad-status");
const controlsToggle = document.querySelector("#controls-toggle");
const controlsPanel = document.querySelector("#controls-panel");
const mappingButtons = document.querySelectorAll("[data-map-control]");
const shaderButton = document.querySelector("#shader-cycle");
const shaderCanvas = document.querySelector("#shader-screen");
const shaderName = document.querySelector("#shader-name");
// Ordre du cycle du bouton shader ; "" = aucun. Les noms affichés viennent des manifest.ini.
const SHADER_CYCLE = [
  "", "lcd.shader", "gba-color.shader", "agb001.shader", "ags001.shader",
  "scanlines.shader", "tv-mode.shader", "vba_pixelate.shader", "scale2x.shader",
  "scale4x.shader", "soften.shader", "motion_blur.shader", "vignette.shader", "wiiu.shader",
];

const STORAGE_KEY = "backstage-html-proto-controls";
const DEFAULT_GAMEPAD_MAPPING = {
  up: 12, down: 13, left: 14, right: 15,
  a: 0, b: 1, l: 4, r: 5, start: 9, select: 8,
};
// Touches physiques (KeyboardEvent.code) : la position ne dépend pas de la
// disposition du clavier, seul le libellé affiché en dépend.
const DEFAULT_KEYBOARD_MAPPING = {
  up: "ArrowUp", down: "ArrowDown", left: "ArrowLeft", right: "ArrowRight",
  a: "KeyZ", b: "KeyX", l: "KeyQ", r: "KeyE", start: "Enter", select: "ShiftRight",
};
const CONTROL_NAMES = {
  up: "Haut", down: "Bas", left: "Gauche", right: "Droite",
  a: "A", b: "B", l: "L", r: "R", select: "Select", start: "Start",
};
const KEY_NAMES = {
  ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→",
  Enter: "Entrée", Space: "Espace", Backspace: "Retour arrière", Tab: "Tab",
  ShiftLeft: "Maj. gauche", ShiftRight: "Maj. droite",
  ControlLeft: "Ctrl gauche", ControlRight: "Ctrl droite",
  AltLeft: "Alt", AltRight: "Alt Gr",
};

let emulator;
let cartridgeSave;
let gameRunning = false;
let selectedRom;
let frameUrl;
let muted = false;
// Affectation en cours de saisie : { device: "keyboard" | "gamepad", control }.
let capture = null;
let keyboardLayout = null;
const heldKeys = new Map();
let previousButtons = [];
const activeInputs = new Map();
let savedControls = {};
try {
  savedControls = JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? {};
} catch {
  // Un cadre intégré peut interdire l'accès au stockage.
}
const gamepadMapping = { ...DEFAULT_GAMEPAD_MAPPING, ...savedControls.gamepad };
const keyboardMapping = { ...DEFAULT_KEYBOARD_MAPPING, ...savedControls.keyboard };

function setStatus(message) {
  status.textContent = message;
}

function setControlsEnabled(enabled) {
  muteButton.disabled = !enabled;
  fullscreenButton.disabled = !enabled || !document.fullscreenEnabled;
}

function saveControls() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      // Le choix du contour n'existe que dans la page du prototype.
      ...(frameStyle && { frameStyle: frameStyle.value === "image" ? "backstage" : frameStyle.value }),
      gamepad: gamepadMapping,
      keyboard: keyboardMapping,
      shader: shaderFolder,
    }));
  } catch {
    // Les réglages restent utilisables pendant la session.
  }
}

function press(control, source) {
  if (!gameRunning) return;
  const sources = activeInputs.get(control) || new Set();
  if (!sources.size) emulator.setButton(control, true);
  sources.add(source);
  activeInputs.set(control, sources);
}

function release(control, source) {
  const sources = activeInputs.get(control);
  if (!sources) return;
  sources.delete(source);
  if (!sources.size) {
    emulator?.setButton(control, false);
    activeInputs.delete(control);
  }
}

function keyName(code) {
  const label = keyboardLayout?.get(code);
  if (label && label.trim()) return label.toUpperCase();
  return KEY_NAMES[code] ?? code.replace(/^(Key|Digit)/, "");
}

function refreshMappingButtons() {
  mappingButtons.forEach((button) => {
    const { mapDevice: device, mapControl: control } = button.dataset;
    const name = CONTROL_NAMES[control];
    const keyboard = device === "keyboard";
    const assignment = keyboard ? keyName(keyboardMapping[control]) : `Bouton ${gamepadMapping[control] + 1}`;
    const listening = capture?.device === device && capture.control === control;
    button.textContent = listening ? "…" : assignment;
    button.classList.toggle("listening", listening);
    button.setAttribute("aria-label", listening
      ? `${keyboard ? "Appuie sur une touche du clavier" : "Appuie sur un bouton de la manette"} pour ${name}. Échap ou un second clic pour annuler.`
      : `Modifier ${keyboard ? "la touche" : "le bouton de manette"} de ${name}, ${assignment}`);
  });
}

function pollGamepad() {
  let gamepad;
  try {
    gamepad = [...navigator.getGamepads()].find(Boolean);
  } catch {
    gamepadStatus.textContent = "La manette n’est pas disponible dans ce cadre.";
    return;
  }
  if (gamepad) {
    gamepadStatus.textContent = `Manette connectée : ${gamepad.id}`;
    const pressedButtons = gamepad.buttons.map((button) => button.pressed || button.value > .6);
    if (capture?.device === "gamepad") {
      const captured = pressedButtons.findIndex((pressed, index) => pressed && !previousButtons[index]);
      if (captured >= 0) {
        gamepadMapping[capture.control] = captured;
        capture = null;
        saveControls();
        refreshMappingButtons();
      }
    }
    for (const [control, buttonIndex] of Object.entries(gamepadMapping)) {
      const source = `gamepad-${control}`;
      const stickPressed = {
        left: gamepad.axes[0] < -.55,
        right: gamepad.axes[0] > .55,
        up: gamepad.axes[1] < -.55,
        down: gamepad.axes[1] > .55,
      }[control] || false;
      if (pressedButtons[buttonIndex] || stickPressed) press(control, source);
      else release(control, source);
    }
    previousButtons = pressedButtons;
  } else {
    gamepadStatus.textContent = "Branche une manette ou appuie sur l’un de ses boutons.";
    previousButtons = [];
  }
  requestAnimationFrame(pollGamepad);
}

// Build WEB embarque la ROM (rom.js) et le moteur (vendor/mgba.wasm.js) en base64 :
// une page ouverte depuis le disque (file://) n'a pas le droit de les télécharger.
function decodeBase64(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

const engineWasm = globalThis.BACKSTAGE_MGBA_WASM ? decodeBase64(globalThis.BACKSTAGE_MGBA_WASM) : undefined;

function reportSaveError(error) {
  console.warn("Cartridge save unavailable.", error);
  compatibility.textContent = "La sauvegarde du jeu n’est pas accessible dans ce navigateur.";
}

function syncSave() {
  if (!gameRunning || !cartridgeSave) return;
  try {
    cartridgeSave.write(emulator.readSave());
  } catch (error) {
    reportSaveError(error);
  }
}

async function prepareRom(rom) {
  selectedRom = rom;
  playButton.disabled = true;
  emulator?.destroy();
  emulator = null;
  cartridgeSave?.close();
  cartridgeSave = null;
  if (!rom) {
    setStatus("Choisis une ROM .gba");
    return;
  }

  setStatus("Préparation de l’émulateur…");
  let save;
  try {
    save = await openCartridgeSave(rom.name).catch(reportSaveError);
    if (selectedRom !== rom) {
      save?.close();
      return;
    }
    const engine = await load({
      canvasEl: canvas,
      assets: { rom: new Uint8Array(await rom.arrayBuffer()) },
      wasmBinary: engineWasm,
      hostControls: true,
      persist: null,
      options: { system: "gba", gamepads: false, escMenu: false, volume: 1 },
    });
    if (selectedRom !== rom) {
      engine.destroy();
      save?.close();
      return;
    }
    if (save?.contents?.length) {
      try {
        engine.loadSave(new Uint8Array(save.contents));
      } catch (error) {
        reportSaveError(error);
        save.close();
        save = null;
      }
    }
    emulator = engine;
    cartridgeSave = save;
    setStatus(`${rom.name} est prête.`);
    playButton.disabled = false;
  } catch (error) {
    save?.close();
    if (selectedRom !== rom) return;
    console.error(error);
    setStatus("Impossible de préparer l’émulateur pour cette ROM.");
  }
}

async function boot() {
  if (!bundledRom) {
    setStatus("Choisis une ROM .gba");
    return;
  }
  try {
    await prepareRom(new File([decodeBase64(globalThis.BACKSTAGE_ROM)], bundledRom));
  } catch (error) {
    console.error(error);
    setStatus("Impossible de charger la ROM du paquet.");
  }
}

romInput.addEventListener("change", () => {
  if (!gameRunning) prepareRom(romInput.files?.[0]);
});

async function unlockItchOrientation() {
  if (!isItch || window === window.top || !touchPointer.matches || !screen.orientation?.unlock) return;
  try {
    // Sur Firefox, le plein écran du cadre itch.io ne suffit pas pour libérer
    // l'orientation : le document du jeu doit aussi être en plein écran.
    if (isFirefoxAndroid && !document.fullscreenElement && document.fullscreenEnabled) {
      await document.documentElement.requestFullscreen();
    }
    screen.orientation.unlock();
  } catch (error) {
    console.debug("Could not unlock screen orientation", error);
  }
}

playButton.addEventListener("click", () => {
  if (!selectedRom || !emulator) return;
  unlockItchOrientation();
  playButton.disabled = true;
  emulator.start();
  gameRunning = true;
  curtain.classList.add("hidden");
  canvas.inert = false;
  canvas.focus();
  setControlsEnabled(true);
});

muteButton.addEventListener("click", () => {
  muted = !muted;
  emulator.config.write("volume", muted ? 0 : 1);
  muteButton.title = muted ? "Activer le son" : "Couper le son";
  muteButton.setAttribute("aria-label", muteButton.title);
  muteButton.toggleAttribute("data-muted", muted);
});

fullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await player.requestFullscreen();
  } catch {
    compatibility.textContent = "Le plein écran n’est pas disponible dans ce cadre.";
  }
});

document.addEventListener("fullscreenchange", () => {
  const title = document.fullscreenElement ? "Quitter le plein écran" : "Plein écran";
  fullscreenButton.title = title;
  fullscreenButton.setAttribute("aria-label", title);
});

// La vue mobile et le choix du contour n'existent que dans la page du prototype :
// le gabarit exporté les retire, le contour y est fixé par le build.
mobilePreviewButton?.addEventListener("click", () => {
  const active = prototype.classList.toggle("mobile-preview");
  mobilePreviewButton.setAttribute("aria-pressed", String(active));
  previewOrientation.hidden = !active;
  if (active) setControlsPanelOpen(false);
  updateTouchLayout();
});

function updateTouchLayout() {
  const preview = prototype.classList.contains("mobile-preview");
  const landscapeScreen = screen.orientation?.type.startsWith("landscape");
  const landscape = preview ? touchLayout.value === "landscape"
    : touchPointer.matches && (landscapeViewport.matches || landscapeScreen);
  prototype.classList.toggle("preview-landscape", preview && landscape);
  player.classList.toggle("side-controls", landscape);
}

updateTouchLayout();
touchPointer.addEventListener("change", updateTouchLayout);
landscapeViewport.addEventListener("change", updateTouchLayout);
screen.orientation?.addEventListener("change", updateTouchLayout);
touchLayout?.addEventListener("change", updateTouchLayout);

function setControlsPanelOpen(open) {
  controlsPanel.hidden = !open;
  controlsToggle.setAttribute("aria-expanded", String(open));
  if (!open && capture) {
    capture = null;
    refreshMappingButtons();
  }
}

controlsToggle.addEventListener("click", () => setControlsPanelOpen(controlsPanel.hidden));

function updateFrame() {
  const style = frameStyle.value;
  player.dataset.frame = style === "image" && !frameUrl ? "none" : style;
  framePicker.hidden = style !== "image";
}

if (frameStyle) {
  frameStyle.value = savedControls.frameStyle ?? "backstage";
  if (!frameStyle.value || frameStyle.value === "image") frameStyle.value = "backstage";
  updateFrame();
  frameStyle.addEventListener("change", () => {
    updateFrame();
    saveControls();
  });
}

frameFile?.addEventListener("change", async () => {
  const file = frameFile.files[0];
  if (!file) return;

  const url = URL.createObjectURL(file);
  const image = new Image();
  image.src = url;
  frameStatus.textContent = "";
  try {
    await image.decode();
  } catch {
    URL.revokeObjectURL(url);
    if (frameFile.files[0] === file) frameStatus.textContent = "Cette image ne peut pas être ouverte.";
    return;
  }
  if (frameFile.files[0] !== file) {
    URL.revokeObjectURL(url);
    return;
  }
  // Le contour suit la grille native 272 × 208 : une autre taille décalerait le jeu.
  // Une image matricielle doit en être un multiple exact ; un SVG, vectoriel, doit
  // seulement en avoir les proportions (largeur et hauteur ou viewBox).
  const { naturalWidth: width, naturalHeight: height } = image;
  const svg = file.type === "image/svg+xml";
  const scale = width / 272;
  const fits = svg
    ? width > 0 && Math.abs(width * 208 - height * 272) <= width * 2
    : Number.isInteger(scale) && scale >= 1 && height === 208 * scale;
  if (!fits) {
    URL.revokeObjectURL(url);
    frameStatus.textContent = svg
      ? `Le SVG mesure ${width} × ${height} ; il lui faut les proportions de 272 × 208.`
      : `L’image mesure ${width} × ${height} px ; il faut 272 × 208 px ou un multiple exact.`;
    return;
  }

  if (frameUrl) URL.revokeObjectURL(frameUrl);
  frameUrl = url;
  player.style.setProperty("--frame-image", `url("${url}")`);
  updateFrame();
});

mappingButtons.forEach((button) => button.addEventListener("click", () => {
  const { mapDevice: device, mapControl: control } = button.dataset;
  capture = capture?.device === device && capture.control === control ? null : { device, control };
  refreshMappingButtons();
}));

function releaseHeldKeys() {
  for (const [code, control] of heldKeys) release(control, `key-${code}`);
  heldKeys.clear();
}

document.addEventListener("keydown", (event) => {
  if (capture) {
    if (event.code !== "Escape" && capture.device !== "keyboard") return;
    event.preventDefault();
    if (event.code !== "Escape") {
      // Une touche ne commande qu'une action : celle qui l'avait prend l'ancienne touche.
      for (const control of Object.keys(keyboardMapping)) {
        if (keyboardMapping[control] === event.code) keyboardMapping[control] = keyboardMapping[capture.control];
      }
      keyboardMapping[capture.control] = event.code;
      saveControls();
    }
    capture = null;
    refreshMappingButtons();
    return;
  }
  // Le jeu ne lit le clavier qu'une fois lancé, et laisse les champs et
  // l'activation des boutons au navigateur.
  if (!curtain.classList.contains("hidden") || event.target.closest("input, select, textarea")) return;
  if (event.target.closest("button") && ["Enter", "Space"].includes(event.code)) return;
  const control = Object.keys(keyboardMapping).find((name) => keyboardMapping[name] === event.code);
  if (!control) return;
  event.preventDefault();
  if (event.repeat || heldKeys.has(event.code)) return;
  heldKeys.set(event.code, control);
  press(control, `key-${event.code}`);
});

document.addEventListener("keyup", (event) => {
  const control = heldKeys.get(event.code);
  if (!control) return;
  heldKeys.delete(event.code);
  release(control, `key-${event.code}`);
});

window.addEventListener("blur", releaseHeldKeys);

// Libellés des touches selon la disposition réelle du clavier, si le navigateur la donne.
navigator.keyboard?.getLayoutMap?.().then((layout) => {
  keyboardLayout = layout;
  refreshMappingButtons();
}).catch(() => {});

document.querySelectorAll("[data-control]").forEach((button) => {
  const control = button.dataset.control;
  const touches = new Map();
  button.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || touches.has(event.pointerId)) return;
    event.preventDefault();
    button.setPointerCapture(event.pointerId);
    // Un nouvel appui peut réutiliser le même pointerId avant la fin du délai.
    const source = Symbol();
    touches.set(event.pointerId, { source, started: performance.now() });
    press(control, source);
  });
  for (const eventName of ["pointerup", "pointercancel", "lostpointercapture"]) {
    button.addEventListener(eventName, (event) => {
      const touch = touches.get(event.pointerId);
      if (!touch) return;
      touches.delete(event.pointerId);
      // L'émulateur doit pouvoir lire un appui bref sur au moins une frame.
      const delay = eventName === "pointerup" ? 45 - (performance.now() - touch.started) : 0;
      if (delay > 0) setTimeout(() => release(control, touch.source), delay);
      else release(control, touch.source);
    });
  }
});

// Pavé directionnel à glisser : la position du doigt choisit l'un des huit
// secteurs de 45°, ce qui donne les diagonales sans viser deux boutons.
const stick = document.querySelector(".touch-stick");
const stickKnob = stick.querySelector(".stick-knob");
const STICK_SECTORS = [
  ["right"], ["right", "down"], ["down"], ["left", "down"],
  ["left"], ["left", "up"], ["up"], ["right", "up"],
];
const stickHeld = new Map();
let stickPointer = null;
let stickPresses = 0;

function setStickDirections(directions) {
  for (const [direction, held] of stickHeld) {
    if (directions.includes(direction)) continue;
    stickHeld.delete(direction);
    // Même garde que les boutons : un appui reste actif au moins 45 ms.
    setTimeout(() => release(direction, held.source), Math.max(0, 45 - (performance.now() - held.started)));
  }
  for (const direction of directions) {
    if (stickHeld.has(direction)) continue;
    const source = `stick-${direction}-${stickPresses++}`;
    stickHeld.set(direction, { source, started: performance.now() });
    press(direction, source);
  }
  stick.querySelectorAll(".stick-mark").forEach((mark) => {
    mark.classList.toggle("lit", stickHeld.has(mark.dataset.direction));
  });
}

function moveStick(event) {
  const rect = stick.getBoundingClientRect();
  const radius = rect.width / 2;
  const dx = event.clientX - (rect.left + radius);
  const dy = event.clientY - (rect.top + radius);
  const distance = Math.hypot(dx, dy);
  const travel = Math.min(distance, radius * .5);
  const scale = distance ? travel / distance : 0;
  stickKnob.style.translate = `${dx * scale}px ${dy * scale}px`;
  if (distance < radius * .25) {
    setStickDirections([]);
    return;
  }
  const sector = (Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) + 8) % 8;
  setStickDirections(STICK_SECTORS[sector]);
}

function releaseStick(event) {
  if (event.pointerId !== stickPointer) return;
  stickPointer = null;
  stick.classList.remove("held");
  stickKnob.style.translate = "";
  setStickDirections([]);
}

stick.addEventListener("pointerdown", (event) => {
  if (stickPointer !== null) return;
  event.preventDefault();
  stick.setPointerCapture(event.pointerId);
  stickPointer = event.pointerId;
  stick.classList.add("held");
  moveStick(event);
});
stick.addEventListener("pointermove", (event) => {
  if (event.pointerId === stickPointer) moveStick(event);
});
for (const eventName of ["pointerup", "pointercancel", "lostpointercapture"]) {
  stick.addEventListener(eventName, releaseStick);
}

let shaderScreen;
let shaderFolder = SHADER_CYCLE.includes(savedControls.shader) ? savedControls.shader : "";
let shaderNameTimer = 0;
try {
  shaderScreen = new ShaderScreen(shaderCanvas, canvas);
} catch (error) {
  console.error(error);
  shaderButton.hidden = true;
}

function showShaderName(name) {
  shaderName.textContent = name;
  shaderName.hidden = false;
  clearTimeout(shaderNameTimer);
  shaderNameTimer = setTimeout(() => { shaderName.hidden = true; }, 1200);
}

async function applyShader({ announce }) {
  const folder = shaderFolder;
  let name = "Aucun shader";
  try {
    const shader = folder ? await loadShader(folder) : null;
    if (folder !== shaderFolder) return;
    shaderScreen.setShader(shader);
    if (shader) name = shader.name;
  } catch (error) {
    console.error(error);
    compatibility.textContent = "Ce shader ne fonctionne pas dans ce navigateur.";
    shaderFolder = "";
    shaderScreen.setShader(null);
  }
  shaderButton.setAttribute("aria-pressed", String(Boolean(shaderFolder)));
  shaderButton.title = `Shader : ${shaderFolder ? name : "aucun"}`;
  shaderButton.setAttribute("aria-label", shaderButton.title);
  if (announce) showShaderName(name);
  saveControls();
}

if (shaderScreen) {
  applyShader({ announce: false });
  shaderButton.addEventListener("click", () => {
    shaderFolder = SHADER_CYCLE[(SHADER_CYCLE.indexOf(shaderFolder) + 1) % SHADER_CYCLE.length];
    applyShader({ announce: true });
  });
}

setInterval(syncSave, 5000);
window.addEventListener("pagehide", syncSave);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) syncSave();
});
refreshMappingButtons();
pollGamepad();
boot();
