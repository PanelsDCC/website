import ejs from "ejs";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const srcRoot = path.resolve(root, "src");
const pagesDir = path.join(srcRoot, "pages");
const distDir = path.join(root, "dist");
const siteConfigPath = path.join(srcRoot, "site-config.json");

function walkEjs(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) walkEjs(full, out);
    else if (name.endsWith(".ejs")) out.push(full);
  }
  return out;
}

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) return;
  const st = fs.statSync(src);
  if (st.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const name of fs.readdirSync(src)) {
      copyRecursive(path.join(src, name), path.join(dest, name));
    }
  } else {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
  }
}

function buildVendorData() {
  const templatePath = path.join(root, "vendor-data.template");
  const outPath = path.join(root, "vendor-data");
  const progressDir = path.join(root, "scripts", "progress");
  if (!fs.existsSync(templatePath)) {
    console.warn("vendor-data.template missing; skipping vendor-data embed");
    return;
  }
  const statusPy = fs.readFileSync(path.join(progressDir, "progress_status.py"), "utf8");
  const serverPy = fs.readFileSync(path.join(progressDir, "server.py"), "utf8");
  // Strip leading shebang from embedded copies (shell already invokes python3)
  const stripShebang = (s) => s.replace(/^#![^\n]*\n/, "");
  let out = fs.readFileSync(templatePath, "utf8");
  out = out.replace("@@PROGRESS_STATUS_PY@@", stripShebang(statusPy).replace(/\r\n/g, "\n"));
  out = out.replace("@@PROGRESS_SERVER_PY@@", stripShebang(serverPy).replace(/\r\n/g, "\n"));
  if (out.includes("@@PROGRESS_")) {
    throw new Error("vendor-data embed failed: placeholder left unsubstituted");
  }
  fs.writeFileSync(outPath, out.replace(/\r\n/g, "\n"), "utf8");
  console.log("wrote", path.relative(root, outPath), "(embedded progress UI)");
}

function buildAll() {
  fs.rmSync(distDir, { recursive: true, force: true });
  fs.mkdirSync(distDir, { recursive: true });

  buildVendorData();

  // Static assets (repo root source of truth)
  copyRecursive(path.join(root, "images"), path.join(distDir, "images"));
  if (fs.existsSync(path.join(root, "videos")))
    copyRecursive(path.join(root, "videos"), path.join(distDir, "videos"));
  if (fs.existsSync(path.join(root, "style.css")))
    fs.copyFileSync(path.join(root, "style.css"), path.join(distDir, "style.css"));
  for (const f of ["CNAME", "install.sh", "vendor-data"]) {
    const p = path.join(root, f);
    if (fs.existsSync(p)) fs.copyFileSync(p, path.join(distDir, f));
  }
  // Progress sources for local replay / reference (Pi uses embedded copy in vendor-data)
  copyRecursive(path.join(root, "scripts", "progress"), path.join(distDir, "progress"));
  // Do not ship the large fixture log or tests on the public site tree optionally —
  // keep fixtures for local unittest; strip tests from dist to reduce noise.
  const distProgress = path.join(distDir, "progress");
  for (const drop of ["test_progress_status.py", "fixtures", "__pycache__"]) {
    const p = path.join(distProgress, drop);
    fs.rmSync(p, { recursive: true, force: true });
  }

  const files = walkEjs(pagesDir);
  const viewsPartials = path.join(srcRoot, "templates", "partials");
  let panelsAppOrigin = "https://dev.app.panelsd.cc";
  if (fs.existsSync(siteConfigPath)) {
    try {
      const sc = JSON.parse(fs.readFileSync(siteConfigPath, "utf8"));
      if (sc.panelsAppOrigin && typeof sc.panelsAppOrigin === "string") {
        panelsAppOrigin = sc.panelsAppOrigin.replace(/\/$/, "");
      }
    } catch (e) {
      console.warn("site-config.json:", e.message);
    }
  }
  const common = { srcRoot, basePath: "", panelsAppOrigin };

  for (const inPath of files) {
    const relFromPages = path.relative(pagesDir, inPath);
    const outRel = relFromPages.replace(/\.ejs$/i, ".html");
    const outPath = path.join(distDir, outRel);
    const template = fs.readFileSync(inPath, "utf8");
    const html = ejs.render(template, common, {
      filename: inPath,
      views: [viewsPartials],
    });
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, html, "utf8");
    console.log("wrote", path.relative(root, outPath));
  }
}

const watch = process.argv.includes("--watch");
buildAll();
if (watch) {
  let t = null;
  const debounce = () => {
    clearTimeout(t);
    t = setTimeout(() => {
      try {
        buildAll();
      } catch (e) {
        console.error(e);
      }
    }, 150);
  };
  fs.watch(path.join(srcRoot, "pages"), { recursive: true }, debounce);
  fs.watch(path.join(srcRoot, "templates"), { recursive: true }, debounce);
  fs.watch(path.join(root, "style.css"), debounce);
  fs.watch(siteConfigPath, debounce);
  const progressDir = path.join(root, "scripts", "progress");
  if (fs.existsSync(progressDir)) fs.watch(progressDir, { recursive: true }, debounce);
  if (fs.existsSync(path.join(root, "vendor-data.template")))
    fs.watch(path.join(root, "vendor-data.template"), debounce);
  console.log("watching src/pages, src/templates, site-config.json, style.css, progress …");
}
