// OsteoAve: pantallas, envío del archivo a la API y visores 3D.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const $ = (id) => document.getElementById(id);
const num = (x, dec = 2) => x.toLocaleString("es-AR", { minimumFractionDigits: dec, maximumFractionDigits: dec });
const pct = (p) => (p < 0.005 ? "menos de 1%" : `${Math.round(p * 100)}%`);
const sinMovimiento = matchMedia("(prefers-reduced-motion: reduce)").matches;

let coleccion = null;          // respuesta de /api/coleccion
let resultado = null;          // última respuesta de /api/identificar
let nombreArchivo = "";
// Sin servidor (por ejemplo en GitHub Pages) o con ?demo en la dirección, la página usa
// respuestas grabadas en demo/ para poder probar la interfaz.
let demo = new URLSearchParams(location.search).has("demo");
const hayServidor = demo ? Promise.resolve(false)
  : fetch("api/salud").then((r) => r.ok).catch(() => false);

// ---------------------------------------------------------------------------
// Navegación entre pantallas (#inicio, #identificar, #resultado, #coleccion)
// ---------------------------------------------------------------------------

const menu = $("nav-menu"), links = $("nav-links");
menu.addEventListener("click", () => {
  const abierto = links.classList.toggle("abierto");
  menu.classList.toggle("abierto", abierto);
  menu.setAttribute("aria-expanded", String(abierto));
});

function mostrarPantalla() {
  let id = location.hash.slice(1) || "inicio";
  if (id === "resultado" && !resultado) id = "identificar";
  if (!document.getElementById(id)?.hasAttribute("data-pantalla")) id = "inicio";
  document.querySelectorAll("[data-pantalla]").forEach((s) => (s.hidden = s.id !== id));
  document.querySelectorAll(".nav__links a").forEach((a) => {
    if (a.getAttribute("href") === `#${id}`) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  links.classList.remove("abierto"); menu.classList.remove("abierto"); menu.setAttribute("aria-expanded", "false");
  window.scrollTo(0, 0);
  if (id === "coleccion") cargarColeccion();
  if (id === "resultado") visorMapa?.redimensionar();
}
addEventListener("hashchange", mostrarPantalla);

// ---------------------------------------------------------------------------
// Visor 3D
// ---------------------------------------------------------------------------

const PARADAS = ["#2f4f3e", "#5a7d5a", "#e8e0d0", "#c1663f", "#8f3f1f"].map((c) => new THREE.Color(c));
function colorDistancia(d, max = 1.5) {
  const x = Math.min(Math.max(d / max, 0), 1) * (PARADAS.length - 1);
  const i = Math.min(Math.floor(x), PARADAS.length - 2);
  return PARADAS[i].clone().lerp(PARADAS[i + 1], x - i);
}

function crearVisor(contenedor, { controles = true, fondo = 0xfbf9f4, girar = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(fondo);
  contenedor.replaceChildren(renderer.domElement);
  const escena = new THREE.Scene();
  const camara = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
  escena.add(new THREE.HemisphereLight(0xffffff, 0x8a8578, 1.4));
  const luz = new THREE.DirectionalLight(0xffffff, 1.6);
  camara.add(luz); luz.position.set(1, 1, 2); escena.add(camara);
  const ctrl = controles ? new OrbitControls(camara, renderer.domElement) : null;
  if (ctrl) { ctrl.enableDamping = true; }
  let objeto = null, girando = girar && !sinMovimiento;

  function redimensionar() {
    const w = contenedor.clientWidth || 300, h = contenedor.clientHeight || 300;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camara.aspect = w / h; camara.updateProjectionMatrix();
  }
  function poner(obj) {
    if (objeto) { escena.remove(objeto); objeto.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); }); }
    // el modelo puede estar lejos del origen: se centra dentro de un pivote, que es lo que gira
    const caja = new THREE.Box3().setFromObject(obj), centro = caja.getCenter(new THREE.Vector3());
    const radio = caja.getSize(new THREE.Vector3()).length() / 2;
    obj.position.sub(centro);
    objeto = new THREE.Group(); objeto.add(obj); escena.add(objeto);
    redimensionar();
    camara.position.set(radio * 1.6, radio * 1.1, radio * 2.4);
    camara.near = radio / 50; camara.far = radio * 50; camara.updateProjectionMatrix();
    camara.lookAt(0, 0, 0); ctrl?.target.set(0, 0, 0);
  }
  renderer.setAnimationLoop(() => {
    if (girando && objeto) objeto.rotation.y += 0.01;
    ctrl?.update(); renderer.render(escena, camara);
  });
  new ResizeObserver(redimensionar).observe(contenedor);
  return {
    redimensionar,
    malla(geom) {
      geom.computeVertexNormals();
      poner(new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ color: 0xf2ede0, roughness: 0.8 })));
    },
    puntos(consulta, distancias, referencia) {
      const grupo = new THREE.Group();
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(consulta.flat(), 3));
      const colores = distancias.flatMap((d) => colorDistancia(d).toArray());
      g.setAttribute("color", new THREE.Float32BufferAttribute(colores, 3));
      const tam = Math.max(...consulta.map((p) => Math.abs(p[0]))) / 40;
      grupo.add(new THREE.Points(g, new THREE.PointsMaterial({ size: tam, vertexColors: true })));
      const gr = new THREE.BufferGeometry();
      gr.setAttribute("position", new THREE.Float32BufferAttribute(referencia.flat(), 3));
      grupo.add(new THREE.Points(gr, new THREE.PointsMaterial({ size: tam * 0.7, color: 0x8a8578, transparent: true, opacity: 0.25 })));
      poner(grupo);
    },
  };
}

// ---------------------------------------------------------------------------
// Elegir archivo y vista previa
// ---------------------------------------------------------------------------

const entrada = $("archivo"), zona = $("subir");
let visorPrevia = null, visorMapa = null;

async function leerGeometria(archivo) {
  const ext = archivo.name.split(".").pop().toLowerCase();
  const datos = ext === "obj" ? await archivo.text() : await archivo.arrayBuffer();
  if (ext === "ply") return new PLYLoader().parse(datos);
  if (ext === "stl") return new STLLoader().parse(datos);
  if (ext === "obj") {
    const geoms = [];
    new OBJLoader().parse(datos).traverse((o) => o.isMesh && geoms.push(o.geometry));
    return geoms[0] ?? null;
  }
  return null;                                    // OFF: sin vista previa
}

async function elegirArchivo(archivo) {
  if (!archivo) return;
  nombreArchivo = archivo.name;
  $("archivo-elegido").hidden = false;
  $("archivo-nombre").textContent = archivo.name;
  $("archivo-detalle").textContent = `${num(archivo.size / 1048576, 1)} MB`;
  $("error").hidden = true;
  try {
    const geom = await leerGeometria(archivo);
    if (!geom) return;
    geom.computeBoundingBox();
    const t = geom.boundingBox.getSize(new THREE.Vector3());
    const largo = Math.max(t.x, t.y, t.z);
    const unidades = largo < 1 || largo > 200 ? " · revisá que esté en mm" : " mm";
    $("archivo-detalle").textContent = `${num(archivo.size / 1048576, 1)} MB · ${[t.x, t.y, t.z].map((v) => num(v, 0)).join(" × ")}${unidades}`;
    visorPrevia ??= crearVisor($("visor-previa"), { controles: false, fondo: 0x2f4f3e, girar: true });
    visorPrevia.malla(geom);
  } catch {
    // la vista previa es opcional: si el navegador no puede leer el archivo, igual se puede enviar
  }
}
entrada.addEventListener("change", () => elegirArchivo(entrada.files[0]));
["dragenter", "dragover"].forEach((t) => zona.addEventListener(t, (e) => { e.preventDefault(); zona.classList.add("arrastrando"); }));
["dragleave", "drop"].forEach((t) => zona.addEventListener(t, () => zona.classList.remove("arrastrando")));
zona.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files.length) { entrada.files = e.dataTransfer.files; elegirArchivo(entrada.files[0]); }
});

// ---------------------------------------------------------------------------
// Enviar y mostrar el resultado
// ---------------------------------------------------------------------------

function mostrarError(texto) { $("error").textContent = texto; $("error").hidden = false; }

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const archivo = entrada.files[0];
  if (demo) { await mostrarEjemplo(); return; }
  if (!archivo) { mostrarError("Elegí primero el archivo del modelo."); return; }
  const datos = new FormData();
  datos.append("archivo", archivo);
  datos.append("fragmento", $("fragmento").checked ? "true" : "false");
  datos.append("region", $("region").value);
  const total = coleccion?.vertebras;
  $("cargando-texto").textContent = total ? `Comparando con ${total} vértebras de la colección…` : "Comparando con la colección…";
  $("cargando").hidden = false; $("comparar").disabled = true;
  try {
    const r = await fetch("api/identificar", { method: "POST", body: datos });
    const cuerpo = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(cuerpo.detail || `El servidor respondió con un error (${r.status}).`);
    resultado = cuerpo;
    pintarResultado();
    location.hash = "#resultado";
  } catch (err) {
    mostrarError(err.message === "Failed to fetch" ? "No se pudo conectar con el servidor. Probá de nuevo en un momento." : err.message);
  } finally {
    $("cargando").hidden = true; $("comparar").disabled = false;
  }
});

async function mostrarEjemplo() {
  $("cargando-texto").textContent = "Cargando el resultado de ejemplo…";
  $("cargando").hidden = false;
  try {
    const [r] = await Promise.all([fetch("demo/identificar.json").then((x) => x.json()),
      new Promise((ok) => setTimeout(ok, 1200))]);   // una pausa breve, como la de una comparación real
    resultado = r; nombreArchivo = r.demo.archivo;
    pintarResultado();
    location.hash = "#resultado";
  } catch {
    mostrarError("No se pudo cargar el ejemplo.");
  } finally {
    $("cargando").hidden = true;
  }
}
$("ejemplo").addEventListener("click", mostrarEjemplo);

function nombreEspecie(c) { return c.nombre_comun || c.nombre_cientifico || c.id_especie; }

function pintarResultado() {
  const r = resultado, [m, ...otras] = r.candidatas;
  $("res-nombre").textContent = nombreArchivo;
  $("res-detalle").textContent = (r.demo ? `Ejemplo: ${r.demo.descripcion}. ` : "")
    + `${r.tamano_mm.map((v) => num(v, 0)).join(" × ")} mm · comparada con ${r.comparadas} vértebras`
    + (r.fragmento ? " · como fragmento" : "") + ` · ${num(r.segundos, 1)} s`;
  const umbral = $("res-umbral");
  umbral.hidden = !r.supera_umbral;
  if (r.supera_umbral) umbral.textContent = `La pieza más parecida difiere ${num(m.distancia_mm)} mm, más que el umbral de ${num(r.umbral_mm)} mm: puede que no haya nada parecido en la colección.`;
  $("res-limpieza").hidden = !r.limpieza;
  if (r.limpieza) $("res-limpieza").textContent = `Antes de comparar ${r.limpieza}.`;

  const p = $("res-principal");
  p.replaceChildren();
  const cabeza = el("div", "principal__cabeza", [
    el("p", "mini", "Más probable"),
    el("h2", "principal__especie", nombreEspecie(m)),
    m.nombre_comun && m.nombre_cientifico ? el("p", "principal__cientifico", m.nombre_cientifico) : null,
    el("div", "principal__pos", [el("span", "chip", m.codigo), el("span", null, `${m.region} ${m.posicion}`)]),
  ]);
  const datos = el("div", "principal__datos", [
    el("div", null, [el("p", "dato__etiqueta", "Prob. relativa"), el("p", "dato__valor", pct(m.probabilidad))]),
    el("div", null, [el("p", "dato__etiqueta", "Diferencia media"), el("p", "dato__valor", `${num(m.distancia_mm)} mm`)]),
    el("p", "principal__ref", `Vértebra más parecida: ${m.codigo} de ${m.individuo}`),
  ]);
  p.append(cabeza, datos);

  $("res-otras").replaceChildren(...otras.map((c) => {
    const barra = el("div", "barra", [el("span")]);
    barra.firstChild.style.width = `${Math.max(1, Math.round(c.probabilidad * 100))}%`;
    return el("li", "candidata", [
      el("span", "chip", c.codigo),
      el("div", "candidata__cuerpo", [
        el("div", "candidata__fila", [el("span", null, nombreEspecie(c)), el("strong", null, pct(c.probabilidad))]),
        barra,
        el("div", "candidata__dist", `Diferencia media ${num(c.distancia_mm)} mm · ${c.individuo}`),
      ]),
    ]);
  }));
  if (!otras.length) $("res-otras").append(el("li", "vacio", "No hay otras candidatas."));

  $("res-mapa-ayuda").textContent = `La pieza consultada, alineada con la ${m.codigo} de ${m.individuo} (en gris) y coloreada según la distancia entre superficies.`;
  visorMapa ??= crearVisor($("visor-mapa"));
  visorMapa.puntos(r.mapa.consulta, r.mapa.distancias, r.mapa.referencia);
}

function el(tag, clase, hijos) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (typeof hijos === "string") n.textContent = hijos;
  else if (Array.isArray(hijos)) n.append(...hijos.filter(Boolean));
  return n;
}

// ---------------------------------------------------------------------------
// Colección
// ---------------------------------------------------------------------------

let filtroRegion = "", textoBuscado = "";

async function cargarColeccion() {
  if (!coleccion) {
    try {
      const sinServidor = !(await hayServidor);
      const r = await fetch(sinServidor ? "demo/coleccion.json" : "api/coleccion");
      if (!r.ok) throw new Error();
      coleccion = await r.json();
    } catch {
      $("col-resumen").textContent = "No se pudo cargar la colección.";
      return;
    }
  }
  const c = coleccion;
  $("col-resumen").textContent = `${c.vertebras} vértebras de ${c.individuos} individuos y ${c.especies.length} especies`;
  const opciones = [{ region: "", nombre: "Todas", n: c.vertebras }, ...c.regiones.map((r) => ({ region: r.region, nombre: r.region, n: r.vertebras }))];
  $("col-filtros").replaceChildren(...opciones.map((o) => {
    const b = el("button", `filtro${o.region === filtroRegion ? " activo" : ""}`, [o.nombre + " ", el("span", "filtro__n", String(o.n))]);
    b.type = "button"; b.setAttribute("aria-pressed", String(o.region === filtroRegion));
    b.addEventListener("click", () => { filtroRegion = o.region; cargarColeccion(); });
    return b;
  }));
  const t = textoBuscado.trim().toLowerCase();
  const lista = c.especies.filter((e) => (!filtroRegion || e.regiones[filtroRegion])
    && (!t || [e.nombre_comun, e.nombre_cientifico, e.id_especie].some((x) => x?.toLowerCase().includes(t))));
  $("col-especies").replaceChildren(...lista.map((e) => el("li", "tarjeta especie", [
    el("div", "especie__icono", [icono()]),
    el("div", null, [
      el("h2", "especie__nombre", nombreEspecie(e)),
      e.nombre_comun && e.nombre_cientifico ? el("p", "especie__cientifico", e.nombre_cientifico) : null,
      el("p", "especie__detalle", `${e.individuos} ${e.individuos === 1 ? "individuo" : "individuos"} · ${e.vertebras} vértebras`),
      el("span", `estado${e.evaluable ? " estado--ok" : ""}`, e.evaluable ? "Se puede evaluar" : "Falta un segundo individuo"),
    ]),
  ])));
  if (!lista.length) $("col-especies").append(el("li", "vacio", "No hay especies que coincidan."));
}
$("col-buscar").addEventListener("input", (e) => { textoBuscado = e.target.value; cargarColeccion(); });

function icono() {
  const ns = "http://www.w3.org/2000/svg", s = document.createElementNS(ns, "svg"), p = document.createElementNS(ns, "path");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("width", "28"); s.setAttribute("height", "28"); s.setAttribute("aria-hidden", "true");
  p.setAttribute("d", "M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z M4 7.5l8 4.5 8-4.5 M12 12v9");
  p.setAttribute("fill", "none"); p.setAttribute("stroke", "currentColor"); p.setAttribute("stroke-width", "1.6"); p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
}

hayServidor.then((ok) => {
  demo = !ok;
  $("demo-aviso").hidden = !demo;
  $("ejemplo").hidden = !demo;
  fetch(demo ? "demo/coleccion.json" : "api/coleccion").then((r) => r.ok && r.json())
    .then((c) => { if (c) coleccion = c; }).catch(() => {});
});
mostrarPantalla();
