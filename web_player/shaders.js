// Rendu des shaders de mGBA (dossiers `*.shader` décrits par `manifest.ini`)
// par-dessus l'écran de l'émulateur. La sémantique suit le rendu OpenGL de
// mGBA : chaque passe dessine dans sa propre texture, `texSize` vaut la taille
// native de la console, et une passe `blend=1` se mélange à son image
// précédente (rémanence de l'écran LCD, flou de mouvement).

const NATIVE_SIZE = [240, 160];
// Les shaders sont écrits en GLSL 1.10 ; ils compilent en GLSL ES 3.00 (WebGL 2),
// qui accepte comme mGBA l'indexation d'un tableau par une variable.
const HEADER = "#version 300 es\nprecision highp float;\n";
const DEFAULT_VERTEX = `attribute vec4 position;
varying vec2 texCoord;
void main() {
  gl_Position = position;
  texCoord = (position.st + vec2(1.0, 1.0)) * vec2(0.5, 0.5);
}`;
const DEFAULT_FRAGMENT = `varying vec2 texCoord;
uniform sampler2D tex;
void main() {
  gl_FragColor = texture2D(tex, texCoord);
}`;
const UNIFORM_SIZES = { float: 1, float2: 2, float3: 3, float4: 4 };

function parseIni(text) {
  const sections = {};
  let current = null;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith(";") || line.startsWith("#")) continue;
    const header = line.match(/^\[(.+)\]$/);
    if (header) {
      current = sections[header[1]] = {};
      continue;
    }
    const separator = line.indexOf("=");
    if (current && separator > 0) {
      current[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
    }
  }
  return sections;
}

async function fetchText(url) {
  // Build WEB embarque les shaders dans player.js (file:// interdit fetch).
  const embedded = globalThis.BACKSTAGE_SHADER_FILES?.[new URL(url).pathname.split("/shaders/").at(-1)];
  if (embedded !== undefined) return embedded;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  return response.text();
}

function uniformDefault(name, section) {
  const size = UNIFORM_SIZES[section.type];
  if (!size) throw new Error(`Unsupported uniform type ${section.type} for ${name}.`);
  if (size === 1) return [Number(section.default ?? 0)];
  return Array.from({ length: size }, (_, index) => Number(section[`default[${index}]`] ?? 0));
}

/** Lit un dossier `nom.shader/` et ses fichiers GLSL. */
export async function loadShader(folder) {
  const base = new URL(`shaders/${folder}/`, import.meta.url);
  const manifest = parseIni(await fetchText(new URL("manifest.ini", base)));
  const passes = [];
  for (let index = 0; index < Number(manifest.shader?.passes ?? 0); index++) {
    const section = manifest[`pass.${index}`] ?? {};
    const prefix = `pass.${index}.uniform.`;
    passes.push({
      vertex: section.vertexShader ? await fetchText(new URL(section.vertexShader, base)) : DEFAULT_VERTEX,
      fragment: section.fragmentShader ? await fetchText(new URL(section.fragmentShader, base)) : DEFAULT_FRAGMENT,
      width: Number(section.width ?? 0),
      height: Number(section.height ?? 0),
      blend: section.blend === "1",
      filter: section.filter === "1",
      integerScaling: section.integerScaling === "1",
      uniforms: Object.entries(manifest)
        .filter(([name]) => name.startsWith(prefix))
        .map(([name, values]) => ({ name: name.slice(prefix.length), value: uniformDefault(name, values) })),
    });
  }
  return { name: manifest.shader?.name ?? folder, passes };
}

/** Dessine l'image d'un canvas source à travers un shader mGBA. */
export class ShaderScreen {
  constructor(target, source) {
    this.target = target;
    this.source = source;
    this.passes = [];
    this.frame = 0;
    const gl = target.getContext("webgl2", { alpha: false, antialias: false, depth: false });
    if (!gl) throw new Error("WebGL 2 is not available.");
    this.gl = gl;
    this.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    this.sourceTexture = this.createTexture();
    this.present = this.createProgram(DEFAULT_VERTEX, DEFAULT_FRAGMENT);
    this.draw = this.draw.bind(this);
  }

  createTexture() {
    const gl = this.gl;
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    return texture;
  }

  createProgram(vertexSource, fragmentSource) {
    const gl = this.gl;
    const program = gl.createProgram();
    const vertex = vertexSource
      .replace(/\battribute\b/g, "in")
      .replace(/\bvarying\b/g, "out");
    const fragment = "out vec4 fragColor;\n" + fragmentSource
      .replace(/\bvarying\b/g, "in")
      .replace(/\btexture2D\b/g, "texture")
      .replace(/\bgl_FragColor\b/g, "fragColor");
    for (const [type, source] of [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]]) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, HEADER + source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        const log = gl.getShaderInfoLog(shader);
        gl.deleteShader(shader);
        gl.deleteProgram(program);
        throw new Error(`Shader compilation failed: ${log}`);
      }
      gl.attachShader(program, shader);
      gl.deleteShader(shader);
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const log = gl.getProgramInfoLog(program);
      gl.deleteProgram(program);
      throw new Error(`Shader link failed: ${log}`);
    }
    return program;
  }

  /** Remplace le shader actif ; `null` rend la main à l'écran de l'émulateur. */
  setShader(shader) {
    const gl = this.gl;
    const passes = shader?.passes.map((pass) => ({
      ...pass,
      program: this.createProgram(pass.vertex, pass.fragment),
      texture: this.createTexture(),
      framebuffer: gl.createFramebuffer(),
      size: [0, 0],
    })) ?? [];
    for (const pass of this.passes) {
      gl.deleteProgram(pass.program);
      gl.deleteTexture(pass.texture);
      gl.deleteFramebuffer(pass.framebuffer);
    }
    this.passes = passes;
    this.target.hidden = !passes.length;
    cancelAnimationFrame(this.frame);
    if (passes.length) this.frame = requestAnimationFrame(this.draw);
  }

  passSize(pass, viewport) {
    const size = [pass.width, pass.height].map((value, axis) => {
      if (value < 0) return -value * NATIVE_SIZE[axis];
      return value || viewport[axis];
    });
    if (!pass.integerScaling) return size;
    const scale = Math.max(1, Math.floor(Math.min(size[0] / NATIVE_SIZE[0], size[1] / NATIVE_SIZE[1])));
    return NATIVE_SIZE.map((value) => value * scale);
  }

  drawQuad(program, input, filter) {
    const gl = this.gl;
    gl.useProgram(program);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, input);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.uniform1i(gl.getUniformLocation(program, "tex"), 0);
    gl.uniform2fv(gl.getUniformLocation(program, "texSize"), NATIVE_SIZE);
    const position = gl.getAttribLocation(program, "position");
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  draw() {
    const gl = this.gl;
    const ratio = devicePixelRatio || 1;
    const viewport = [
      Math.max(1, Math.round(this.target.clientWidth * ratio)),
      Math.max(1, Math.round(this.target.clientHeight * ratio)),
    ];
    if (this.target.width !== viewport[0] || this.target.height !== viewport[1]) {
      [this.target.width, this.target.height] = viewport;
    }

    // Le canvas WebGL range sa première ligne en bas : l'image source est retournée à l'envoi.
    gl.bindTexture(gl.TEXTURE_2D, this.sourceTexture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this.source);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);

    let input = this.sourceTexture;
    for (const pass of this.passes) {
      const size = this.passSize(pass, viewport);
      gl.bindTexture(gl.TEXTURE_2D, pass.texture);
      if (pass.size[0] !== size[0] || pass.size[1] !== size[1]) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, size[0], size[1], 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
        gl.bindFramebuffer(gl.FRAMEBUFFER, pass.framebuffer);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, pass.texture, 0);
        pass.size = size;
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, pass.framebuffer);
      gl.viewport(0, 0, size[0], size[1]);
      if (pass.blend) {
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      } else {
        gl.disable(gl.BLEND);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
      }
      gl.useProgram(pass.program);
      for (const uniform of pass.uniforms) {
        const location = gl.getUniformLocation(pass.program, uniform.name);
        gl[`uniform${uniform.value.length}fv`](location, uniform.value);
      }
      this.drawQuad(pass.program, input, pass.filter ? gl.LINEAR : gl.NEAREST);
      input = pass.texture;
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, viewport[0], viewport[1]);
    gl.disable(gl.BLEND);
    this.drawQuad(this.present, input, gl.LINEAR);
    this.frame = requestAnimationFrame(this.draw);
  }
}
