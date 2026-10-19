# SPDX-License-Identifier: GPL-3.0-or-later
"""Texture Library — a browsable texture / material library for IngeTrazo.

An IngeTrazo EXTENSION written from scratch (it is not a port of any other
product's code). It gives IngeTrazo a texture browser in the side tray:

* **Your library**: a folder of images on disk, shown as a thumbnail grid
  with search and category filter. Sub-folders are categories. PBR sets
  (``Brick_Color.jpg`` + ``Brick_Normal.jpg`` + ``Brick_Roughness.jpg`` …)
  appear as ONE entry — the colour map; IngeTrazo textures are single images.
* **Real-world size**: set the width and height of one tile (m, cm, mm, in,
  ft), with an aspect lock and a 0/90/180/270° turn. The size is remembered
  per texture in a small ``<image>.json`` file beside the image.
* **Paint with it**: arms the Paint tool (B) with the texture, so every click
  on a face (or group) paints it, identity included — the material is named
  and registered in the document, so per-material takeoffs stay truthful.
* **Apply to selection**: paints the selected faces / groups in ONE undo
  step, with the same rules as the Paint tool (curved surfaces wrap).
* **Import**: copy images, or the images inside a ``.zip``, into the library.
* **Get online**: optional browser for Poly Haven's CC0 textures
  (polyhaven.com), downloaded one at a time into ``<library>/Poly Haven``.

Install: copy this file into the plugins folder (Extensions ▸ Open plugins
folder) and restart IngeTrazo. The «Textures» tab appears in the side tray;
Extensions ▸ Texture library… (Ctrl+Shift+T) brings it forward.

Textures you add yourself are your responsibility: check their licence
before you publish a model that uses them.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QImageReader, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from core.i18n import current_language

# --------------------------------------------------------------------------
# Words (an extension brings its own; the core catalogues stay the core's)
# --------------------------------------------------------------------------
_TEXTS = {
    "es": {
        "Textures": "Texturas", "Texture library…": "Biblioteca de texturas…",
        "Browse your textures, set their real size and paint with them.":
        "Explora tus texturas, fija su tamaño real y pinta con ellas.",
        "Library": "Biblioteca", "Change…": "Cambiar…", "Open": "Abrir",
        "Rescan": "Actualizar", "Search textures…": "Buscar texturas…",
        "All categories": "Todas las categorías", "Library root": "Raíz",
        "Width": "Ancho", "Height": "Alto", "Keep proportions":
        "Mantener proporciones", "Turn": "Giro", "Remember size":
        "Recordar tamaño", "Paint with it": "Pintar con ella",
        "Apply to selection": "Aplicar a la selección", "Import…":
        "Importar…", "Get online…": "Descargar en línea…",
        "Import downloaded ZIP / images…": "Importar ZIP / imágenes descargados…",
        "{n} textures": "{n} texturas", "No texture selected":
        "Ninguna textura seleccionada", "{w} × {h} px": "{w} × {h} px",
        "Paint tool armed with “{name}” — click faces to paint them":
        "Pincel listo con «{name}»: haz clic en las caras para pintarlas",
        "Select faces or groups first, or use “Paint with it”":
        "Selecciona caras o grupos antes, o usa «Pintar con ella»",
        "“{name}” applied to {n} item(s)": "«{name}» aplicada a {n} elemento(s)",
        "Choose the library folder": "Elige la carpeta de la biblioteca",
        "Import textures": "Importar texturas", "Category (folder name):":
        "Categoría (nombre de carpeta):", "Imported": "Importadas",
        "{n} image(s) imported": "{n} imagen(es) importada(s)",
        "Nothing to import": "No hay nada que importar",
        "Poly Haven textures (CC0)": "Texturas de Poly Haven (CC0)",
        "Search": "Buscar", "Resolution": "Resolución",
        "Download to library": "Descargar a la biblioteca",
        "Loading the list…": "Cargando la lista…",
        "Downloading “{name}”…": "Descargando «{name}»…",
        "Downloaded “{name}”": "«{name}» descargada",
        "Network error: {err}": "Error de red: {err}",
        "{n} shown of {total}": "{n} mostradas de {total}",
        "All textures are CC0 (public domain). polyhaven.com":
        "Todas las texturas son CC0 (dominio público). polyhaven.com",
        "Close": "Cerrar",
    },
}


def _t(text: str, **kw) -> str:
    out = _TEXTS.get(current_language(), {}).get(text, text)
    return out.format(**kw) if kw else out


# --------------------------------------------------------------------------
# Library model — pure functions, no Qt, easy to test
# --------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SCAN_LIMIT = 5000
UNITS = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "ft": 0.3048}

# The last word of a PBR file name says which map it is.
_COLOR_ROLES = {"color", "colour", "albedo", "diffuse", "diff", "basecolor",
                "col", "base"}
_OTHER_ROLES = {
    "normal", "nor", "nrm", "normalgl", "normaldx", "norgl", "nordx",
    "rough", "roughness", "ao", "occlusion", "ambientocclusion", "disp",
    "displacement", "height", "bump", "metal", "metallic", "metalness",
    "spec", "specular", "gloss", "glossiness", "opacity", "alpha", "mask",
    "arm", "orm", "rma", "emissive", "emission", "sss", "preview", "thumb",
    "thumbnail", "icon",
}
_SUFFIX_NOISE = {"gl", "dx"}                      # nor_gl / nor_dx
_RES_RE = re.compile(r"^(\d{1,2}k|jpg|jpeg|png|webp|tif|tiff)$", re.I)


@dataclass
class Entry:
    name: str
    path: Path
    category: str
    tile: tuple | None = None        # (sw, sh) in metres, from the sidecar
    source: str | None = None


def default_root() -> Path:
    try:
        from PySide6.QtCore import QStandardPaths
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericDataLocation)
    except Exception:  # noqa: BLE001
        base = ""
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "IngeTrazo" / "texture_library"


def sidecar_path(image: Path) -> Path:
    return Path(image).with_suffix(".json")


def read_sidecar(image: Path) -> dict:
    try:
        raw = json.loads(sidecar_path(image).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def save_sidecar(image: Path, **fields) -> None:
    """Merge ``fields`` into the image's sidecar (best effort)."""
    data = read_sidecar(image)
    data.update(fields)
    try:
        sidecar_path(image).write_text(
            json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def classify(stem: str) -> tuple[str, str]:
    """``(role, name)`` of an image file stem.

    ``role`` is ``"color"``, ``"other"`` (normal, roughness… — not shown) or
    ``"plain"`` (no map suffix: an ordinary picture, shown). ``name`` is the
    stem without the resolution, the map suffix and the separators; empty
    when nothing is left (a folder-per-texture layout: ``Brick/Color.jpg``).
    """
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", stem) if t]
    while tokens and _RES_RE.match(tokens[-1]):
        tokens.pop()
    # Poly Haven puts the resolution LAST (brick_diff_1k); ambientCG puts it
    # before the map (Brick_1K-JPG_Color). Drop resolution words anywhere.
    tokens = [t for t in tokens if not _RES_RE.match(t)]
    role = "plain"
    if tokens:
        last = tokens[-1].lower()
        if last in _SUFFIX_NOISE and len(tokens) > 1:
            last = tokens[-2].lower()
            drop = 2
        else:
            drop = 1
        if last in _COLOR_ROLES:
            role, tokens = "color", tokens[:-drop]
        elif last in _OTHER_ROLES:
            role = "other"
            tokens = tokens[:-drop]
    if role == "color" and tokens and tokens[-1].lower() in ("base", "col"):
        tokens = tokens[:-1]
    return role, " ".join(tokens)


def scan_library(root: Path, limit: int = SCAN_LIMIT) -> list[Entry]:
    """Every colour image under ``root``; sub-folders are categories."""
    import os
    root = Path(root)
    out: list[Entry] = []
    if not root.is_dir():
        return out
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        here = Path(dirpath)
        rel = here.relative_to(root)
        for fname in sorted(files):
            if fname.startswith("."):
                continue
            p = here / fname
            if p.suffix.lower() not in IMAGE_EXTS:
                continue
            role, name = classify(p.stem)
            if role == "other":
                continue
            category = rel.as_posix() if str(rel) != "." else ""
            if not name:                      # Brick/Color.jpg → "Brick"
                name = here.name if here != root else p.stem
                category = rel.parent.as_posix() if str(rel.parent) != "." \
                    else ""
            meta = read_sidecar(p)
            tile = None
            try:
                sw, sh = float(meta.get("sw", 0)), float(meta.get("sh", 0))
                if sw > 0 and sh > 0:
                    tile = (sw, sh)
            except (TypeError, ValueError):
                tile = None
            out.append(Entry(str(meta.get("name") or name), p,
                             category, tile, meta.get("source")))
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    out.sort(key=lambda e: (e.category.lower(), e.name.lower()))
    return out


def image_size(path: Path) -> tuple[int, int]:
    sz = QImageReader(str(path)).size()
    return (sz.width(), sz.height()) if sz.isValid() else (0, 0)


def default_tile(entry: Entry, px: tuple[int, int]) -> tuple[float, float]:
    """The tile size to start from: the remembered one, else 1 m wide with
    the image's own proportions (so nothing is stretched)."""
    if entry.tile:
        return entry.tile
    w, h = px
    return (1.0, 1.0 * h / w) if w > 0 and h > 0 else (1.0, 1.0)


def texture_dict(path, sw: float, sh: float, rot: float = 0.0) -> dict:
    """The ``attrs["texture"]`` dict IngeTrazo renders (see core.texture)."""
    tex = {"path": str(path), "sw": float(sw), "sh": float(sh)}
    if rot % 360:
        tex["rot"] = float(rot % 360)
    return tex


def unique_material_name(materials: dict, base: str, texture: dict) -> str:
    """The registry name to use for a texture material: ``base`` when free
    or already holding this same recipe, else ``base (2)``… — the rule of
    ``core.materials.register``, without registering."""
    name, n = base or "Texture", 2
    while name in materials:
        other = materials[name]
        if (other.color is None and other.texture == texture
                and other.opacity is None):
            return name
        name = f"{base or 'Texture'} ({n})"
        n += 1
    return name


def selected_faces(scene) -> list:
    from core.mesh import Face
    live = {id(f) for f in scene.mesh.faces}
    return [e for e in scene.selection
            if isinstance(e, Face) and id(e) in live]


def selected_groups(scene) -> list:
    from core.mesh import Face
    groups = list(getattr(scene, "groups", ()) or ())
    return [e for e in scene.selection
            if not isinstance(e, Face) and any(e is g for g in groups)]


def paint_commands(scene, faces: list, groups: list, texture: dict,
                   base_name: str):
    """``(commands, material)`` that paint ``faces`` and ``groups`` with the
    texture the way the Paint tool does: the texture, no translucency, and
    the material's NAME registered and stamped."""
    from core.history import (
        SetFaceMaterialTagCommand, SetFaceOpacityCommand,
        SetFaceTextureCommand, SetGroupMaterialCommand,
    )
    from core.materials import Material
    name = unique_material_name(scene.materials, base_name, texture)
    mat = Material(name, texture=dict(texture))
    cmds: list = []
    if faces:
        wrapped = None
        if len(faces) > 1:                # a curved surface wraps the image
            try:
                from tools.paint import _surface_commands
                wrapped = _surface_commands(scene.mesh, faces, faces[0],
                                            texture, None)
            except Exception:  # noqa: BLE001 — fall back to per-face
                wrapped = None
        cmds += wrapped or [SetFaceTextureCommand(faces, texture)]
        cmds += [SetFaceOpacityCommand(faces, None),
                 SetFaceMaterialTagCommand(faces, name, mat)]
    else:
        cmds.append(SetFaceMaterialTagCommand([], name, mat))
    for g in groups:
        cmds.append(SetGroupMaterialCommand(
            g, {"texture": dict(texture), "mat": name}))
    return cmds, mat


def _safe_segment(text: str, fallback: str) -> str:
    seg = re.sub(r'[\\/:*?"<>|]+', "_", str(text)).strip(" .")
    return seg or fallback


def import_into_library(root: Path, category: str, files: list) -> int:
    """Copy images (and the images inside ``.zip`` files) into
    ``root/category``. Returns how many images came in. Only real image
    bytes are accepted; zip members are written by file name alone."""
    from core.texture import is_image_bytes, is_image_file
    root = Path(root)
    base = root / "/".join(_safe_segment(s, "Imported")
                           for s in str(category).split("/") if s.strip())
    count = 0
    for f in files:
        f = Path(f)
        if f.suffix.lower() == ".zip":
            dest = base / _safe_segment(f.stem, "set")
            try:
                with zipfile.ZipFile(f) as z:
                    for info in z.infolist():
                        member = Path(info.filename)
                        if (info.is_dir() or member.name.startswith(".")
                                or member.suffix.lower() not in IMAGE_EXTS
                                or info.file_size > 100 * 1024 * 1024):
                            continue
                        data = z.read(info)
                        if not is_image_bytes(data):
                            continue
                        dest.mkdir(parents=True, exist_ok=True)
                        (dest / _safe_segment(member.name, "image")
                         ).write_bytes(data)
                        count += 1
            except (OSError, zipfile.BadZipFile):
                continue
        elif f.suffix.lower() in IMAGE_EXTS and is_image_file(f):
            base.mkdir(parents=True, exist_ok=True)
            target = base / f.name
            n = 2
            while target.exists():
                target = base / f"{f.stem} ({n}){f.suffix}"
                n += 1
            shutil.copy2(f, target)
            count += 1
    return count


# --------------------------------------------------------------------------
# Poly Haven (optional, online) — network helpers, patched in tests
# --------------------------------------------------------------------------
USER_AGENT = "IngeTrazo-TextureLibrary/1.0 (+https://github.com/ingelibre/ingetrazo)"
POLY_ASSETS = "https://api.polyhaven.com/assets?t=textures"
POLY_FILES = "https://api.polyhaven.com/files/{id}"
POLY_THUMB = "https://cdn.polyhaven.com/asset_img/thumbs/{id}.png?height=256"
_POLY_HOSTS = ("polyhaven.com", "polyhaven.org")
MAX_DOWNLOAD = 120 * 1024 * 1024


def _check_host(url: str) -> None:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(
            host == h or host.endswith("." + h) for h in _POLY_HOSTS):
        raise ValueError(f"Refusing to download from {host or url!r}")


def _http_get(url: str, timeout: float = 30.0,
              limit: int = MAX_DOWNLOAD) -> bytes:
    _check_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError("The file is larger than the download limit")
    return data


def _http_json(url: str):
    return json.loads(_http_get(url, limit=20 * 1024 * 1024).decode("utf-8"))


def pick_diffuse_url(files: dict, resolution: str):
    """``(url, ext)`` of the colour map in a Poly Haven ``/files`` answer, at
    ``resolution`` (``"1k"``…) or the nearest one below (else the nearest
    above); jpg preferred. ``None`` when there is no colour map."""
    maps = None
    for key in ("Diffuse", "diff", "Color", "albedo"):
        if isinstance(files.get(key), dict):
            maps = files[key]
            break
    if not maps:
        return None

    def kval(r: str) -> int:
        m = re.match(r"^(\d+)k$", str(r).lower())
        return int(m.group(1)) if m else -1

    avail = sorted((r for r in maps if kval(r) > 0), key=kval)
    if not avail:
        return None
    want = kval(resolution)
    below = [r for r in avail if kval(r) <= want]
    res = below[-1] if below else avail[0]
    entry = maps[res]
    for ext in ("jpg", "png"):
        fmt = entry.get(ext) if isinstance(entry, dict) else None
        if isinstance(fmt, dict) and fmt.get("url"):
            return fmt["url"], ext
    return None


def download_poly_asset(root: Path, asset_id: str, name: str,
                        resolution: str) -> Path:
    """Download one texture's colour map into ``root/Poly Haven``; writes a
    sidecar with the source, licence and link. Returns the image path."""
    from core.texture import is_image_bytes
    files = _http_json(POLY_FILES.format(id=asset_id))
    pick = pick_diffuse_url(files, resolution)
    if pick is None:
        raise ValueError("This texture has no colour map")
    url, ext = pick
    data = _http_get(url)
    if not is_image_bytes(data):
        raise ValueError("The download is not an image")
    dest = Path(root) / "Poly Haven"
    dest.mkdir(parents=True, exist_ok=True)
    safe = _safe_segment(asset_id, "texture")
    path = dest / f"{safe}.{ext}"
    path.write_bytes(data)
    save_sidecar(path, name=name, source="Poly Haven", license="CC0",
                 url=f"https://polyhaven.com/a/{asset_id}",
                 resolution=resolution)
    return path


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
ICON_PX = 96


def _icon_for(path: Path, cache: dict) -> QIcon:
    key = str(path)
    if key in cache:
        return cache[key]
    icon = QIcon()
    reader = QImageReader(key)
    reader.setAutoTransform(True)
    sz = reader.size()
    if sz.isValid() and sz.width() > 0 and sz.height() > 0:
        k = min(ICON_PX / sz.width(), ICON_PX / sz.height(), 1.0)
        reader.setScaledSize(QSize(max(1, int(sz.width() * k)),
                                   max(1, int(sz.height() * k))))
    img = reader.read()
    if not img.isNull():
        icon = QIcon(QPixmap.fromImage(img))
    cache[key] = icon
    return icon


def _icon_grid(parent=None) -> QListWidget:
    lw = QListWidget(parent)
    lw.setViewMode(QListView.ViewMode.IconMode)
    lw.setIconSize(QSize(ICON_PX, ICON_PX))
    lw.setGridSize(QSize(ICON_PX + 18, ICON_PX + 36))
    lw.setResizeMode(QListView.ResizeMode.Adjust)
    lw.setMovement(QListView.Movement.Static)
    lw.setWordWrap(True)
    lw.setUniformItemSizes(True)
    lw.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
    return lw


class TextureLibraryPanel(QWidget):
    """The «Textures» tab."""

    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._settings = QSettings("IngeTrazo", "TextureLibraryExtension")
        saved = str(self._settings.value("root", "") or "")
        self._root = Path(saved) if saved else default_root()
        self._entries: list[Entry] = []
        self._shown: list[Entry] = []
        self._icons: dict = {}
        self._pending: list = []
        self._sw = self._sh = 1.0
        self._ratio = 1.0
        self._px = (0, 0)
        self._online = None

        self._tick = QTimer(self)
        self._tick.setSingleShot(True)
        self._tick.timeout.connect(self._load_some_thumbs)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        row = QHBoxLayout()
        self.root_label = QLabel()
        self.root_label.setToolTip(_t("Library root"))
        row.addWidget(QLabel(_t("Library") + ":"))
        row.addWidget(self.root_label, 1)
        b = QToolButton()
        b.setText(_t("Change…"))
        b.clicked.connect(self.choose_root)
        row.addWidget(b)
        b = QToolButton()
        b.setText(_t("Open"))
        b.clicked.connect(self.open_root)
        row.addWidget(b)
        lay.addLayout(row)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("Search textures…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refilter)
        lay.addWidget(self.search)
        self.category = QComboBox()
        self.category.currentIndexChanged.connect(self.refilter)
        lay.addWidget(self.category)

        self.grid = _icon_grid()
        self.grid.currentItemChanged.connect(self._on_select)
        self.grid.itemDoubleClicked.connect(lambda _i: self.paint_with())
        lay.addWidget(self.grid, 1)
        self.count_label = QLabel()
        lay.addWidget(self.count_label)

        self.info = QLabel(_t("No texture selected"))
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        form = QFormLayout()
        self.w_spin, self.h_spin = QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.w_spin, self.h_spin):
            s.setDecimals(3)
            s.setRange(0.001, 100000.0)
        self.w_spin.valueChanged.connect(self._w_edited)
        self.h_spin.valueChanged.connect(self._h_edited)
        self.unit = QComboBox()
        for u in UNITS:
            self.unit.addItem(u, UNITS[u])
        self.unit.setCurrentText(str(self._settings.value("unit", "cm")))
        self.unit.currentIndexChanged.connect(self._unit_changed)
        wrow = QHBoxLayout()
        wrow.addWidget(self.w_spin, 1)
        wrow.addWidget(self.unit)
        form.addRow(_t("Width"), wrow)
        form.addRow(_t("Height"), self.h_spin)
        self.lock = QCheckBox(_t("Keep proportions"))
        self.lock.setChecked(True)
        form.addRow("", self.lock)
        self.rot = QComboBox()
        for deg in (0, 90, 180, 270):
            self.rot.addItem(f"{deg}°", float(deg))
        form.addRow(_t("Turn"), self.rot)
        self.remember = QCheckBox(_t("Remember size"))
        self.remember.setChecked(True)
        form.addRow("", self.remember)
        lay.addLayout(form)

        self.btn_paint = QPushButton(_t("Paint with it"))
        self.btn_paint.clicked.connect(self.paint_with)
        self.btn_apply = QPushButton(_t("Apply to selection"))
        self.btn_apply.clicked.connect(self.apply_selection)
        lay.addWidget(self.btn_paint)
        lay.addWidget(self.btn_apply)

        row = QHBoxLayout()
        for text, fn in ((_t("Get online…"), self.open_online),
                         (_t("Import downloaded ZIP / images…"), self.import_files),
                         (_t("Rescan"), self.rescan)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self._enable_buttons(False)
        QTimer.singleShot(0, self.rescan)

    # ---- library ----------------------------------------------------------
    def _flash(self, text: str) -> None:
        self.status.setText(text)
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            flash(text, 3500)

    def _enable_buttons(self, on: bool) -> None:
        self.btn_paint.setEnabled(on)
        self.btn_apply.setEnabled(on)

    def rescan(self, select: Path | None = None) -> None:
        select = select if isinstance(select, (str, Path)) else None
        self.root_label.setText(self._root.name or str(self._root))
        self.root_label.setToolTip(str(self._root))
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._entries = scan_library(self._root)
        cur = self.category.currentData()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem(_t("All categories"), None)
        for cat in sorted({e.category for e in self._entries if e.category},
                          key=str.lower):
            self.category.addItem(cat, cat)
        i = self.category.findData(cur)
        self.category.setCurrentIndex(max(i, 0))
        self.category.blockSignals(False)
        self.refilter(select=select)

    def refilter(self, *_a, select: Path | None = None) -> None:
        select = select if isinstance(select, (str, Path)) else None
        query = self.search.text().strip().lower()
        cat = self.category.currentData()
        self._shown = [
            e for e in self._entries
            if (cat is None or e.category == cat
                or e.category.startswith(str(cat) + "/"))
            and (not query or query in e.name.lower()
                 or query in e.category.lower())]
        self.grid.blockSignals(True)
        self.grid.clear()
        self._pending = []
        target = None
        for e in self._shown:
            item = QListWidgetItem(e.name)
            item.setToolTip(f"{e.name}\n{e.category or '—'}\n{e.path}")
            item.setSizeHint(QSize(ICON_PX + 18, ICON_PX + 36))
            item.setData(Qt.ItemDataRole.UserRole, str(e.path))
            self.grid.addItem(item)
            self._pending.append((item, e.path))
            if select is not None and Path(select) == e.path:
                target = item
        self.grid.blockSignals(False)
        self.count_label.setText(_t("{n} textures", n=len(self._shown)))
        if target is not None:
            self.grid.setCurrentItem(target)
        else:
            self._on_select(None, None)
        self._tick.start(0)

    def _load_some_thumbs(self) -> None:
        for _ in range(6):
            if not self._pending:
                return
            item, path = self._pending.pop(0)
            try:
                item.setIcon(_icon_for(path, self._icons))
            except RuntimeError:      # the item was cleared meanwhile
                continue
        if self._pending:
            self._tick.start(0)

    def selected_entry(self) -> Entry | None:
        item = self.grid.currentItem()
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        for e in self._shown:
            if str(e.path) == path:
                return e
        return None

    # ---- size controls ----------------------------------------------------
    def _unit_factor(self) -> float:
        return float(self.unit.currentData() or 1.0)

    def _sync_spins(self) -> None:
        k = self._unit_factor()
        for spin, metres in ((self.w_spin, self._sw), (self.h_spin, self._sh)):
            spin.blockSignals(True)
            spin.setValue(metres / k)
            spin.blockSignals(False)

    def _w_edited(self, v: float) -> None:
        self._sw = v * self._unit_factor()
        if self.lock.isChecked() and self._ratio > 0:
            self._sh = self._sw * self._ratio
        self._sync_spins()

    def _h_edited(self, v: float) -> None:
        self._sh = v * self._unit_factor()
        if self.lock.isChecked() and self._ratio > 0:
            self._sw = self._sh / self._ratio
        self._sync_spins()

    def _unit_changed(self, _i: int) -> None:
        self._settings.setValue("unit", self.unit.currentText())
        self._sync_spins()

    def _on_select(self, _cur, _prev) -> None:
        e = self.selected_entry()
        self._enable_buttons(e is not None)
        if e is None:
            self.info.setText(_t("No texture selected"))
            return
        self._px = image_size(e.path)
        self._sw, self._sh = default_tile(e, self._px)
        self._ratio = self._sh / self._sw if self._sw > 0 else 1.0
        self._sync_spins()
        extra = f" — {e.source}" if e.source else ""
        self.info.setText(f"<b>{e.name}</b>{extra}<br>"
                          + _t("{w} × {h} px", w=self._px[0], h=self._px[1]))

    # ---- painting ---------------------------------------------------------
    def _current(self):
        e = self.selected_entry()
        if e is None:
            return None
        tex = texture_dict(e.path, self._sw, self._sh,
                           float(self.rot.currentData() or 0.0))
        if self.remember.isChecked():
            save_sidecar(e.path, sw=round(self._sw, 6), sh=round(self._sh, 6))
            e.tile = (self._sw, self._sh)
        return e, tex

    def paint_with(self) -> None:
        cur = self._current()
        if cur is None:
            return
        e, tex = cur
        from core.materials import Material
        from tools.paint import PaintTool
        name = unique_material_name(self.app.scene.materials, e.name, tex)
        PaintTool.current_texture = dict(tex)
        PaintTool.current_texture_plane = None
        PaintTool.current_material = Material(name, texture=dict(tex))
        PaintTool.current_opacity = None
        PaintTool.current_is_default = False
        win = self.app.window
        activate = getattr(win, "_activate_tool", None)
        if callable(activate):
            activate("paint")
        mats = getattr(getattr(win, "tray", None), "materials", None)
        sync = getattr(mats, "sync_from_paint", None)
        if callable(sync):
            sync()
        self._flash(_t("Paint tool armed with “{name}” — click faces to "
                       "paint them", name=name))

    def apply_selection(self) -> None:
        cur = self._current()
        if cur is None:
            return
        e, tex = cur
        vp = self.app.viewport
        scene = vp.scene
        faces, groups = selected_faces(scene), selected_groups(scene)
        if not faces and not groups:
            self._flash(_t("Select faces or groups first, or use “Paint "
                           "with it”"))
            return
        from core.history import CompoundCommand
        cmds, mat = paint_commands(scene, faces, groups, tex, e.name)
        vp.history.execute(CompoundCommand(cmds))
        notify = getattr(vp, "notify_scene_changed", None)
        if callable(notify):
            notify()
        vp.update()
        self._flash(_t("“{name}” applied to {n} item(s)", name=mat.name,
                       n=len(faces) + len(groups)))

    # ---- library management -----------------------------------------------
    def choose_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, _t("Choose the library folder"), str(self._root))
        if path:
            self._root = Path(path)
            self._settings.setValue("root", path)
            self.rescan()

    def open_root(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._root)))

    def import_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTS)) + " *.zip"
        files, _f = QFileDialog.getOpenFileNames(
            self, _t("Import textures"), "", f"Images (*{exts})".replace(
                "(**", "(*"))
        if not files:
            return
        cat, ok = QInputDialog.getText(
            self, _t("Import textures"), _t("Category (folder name):"),
            text=self.category.currentData() or _t("Imported"))
        if not ok:
            return
        n = import_into_library(self._root, cat, files)
        self._flash(_t("{n} image(s) imported", n=n) if n
                    else _t("Nothing to import"))
        self.rescan()

    def open_online(self) -> None:
        if self._online is None:
            self._online = OnlineDialog(self)
        self._online.show()
        self._online.raise_()
        self._online.activateWindow()


class _Relay(QObject):
    """Carries a worker thread's result to the main thread. A queued
    ``Signal(object)`` on a bound method — see docs/plugins.md."""

    message = Signal(object)


class OnlineDialog(QDialog):
    """Poly Haven's CC0 textures: browse, pick a resolution, download."""

    MAX_SHOWN = 60

    def __init__(self, panel: TextureLibraryPanel) -> None:
        win = panel.app.window
        super().__init__(win if isinstance(win, QWidget) else None)
        self.panel = panel
        self.setWindowTitle(_t("Poly Haven textures (CC0)"))
        self.resize(520, 560)
        self._assets: dict = {}
        self._ids: list = []
        self._thumbs: dict = {}
        self._gen = 0
        self._busy = 0
        self._loaded = False
        self._relay = _Relay(self)
        self._relay.message.connect(self._on_message,
                                    Qt.ConnectionType.QueuedConnection)

        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_t("Search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refilter)
        self.category = QComboBox()
        self.category.currentIndexChanged.connect(self._refilter)
        row.addWidget(self.search, 1)
        row.addWidget(self.category)
        lay.addLayout(row)
        self.grid = _icon_grid()
        self.grid.currentItemChanged.connect(
            lambda *_: self.btn.setEnabled(self._current_id() is not None))
        lay.addWidget(self.grid, 1)
        self.count = QLabel()
        lay.addWidget(self.count)
        row = QHBoxLayout()
        row.addWidget(QLabel(_t("Resolution")))
        self.res = QComboBox()
        for r in ("1k", "2k", "4k"):
            self.res.addItem(r, r)
        self.res.setCurrentText("2k")
        row.addWidget(self.res)
        row.addStretch(1)
        self.btn = QPushButton(_t("Download to library"))
        self.btn.setEnabled(False)
        self.btn.clicked.connect(self._download)
        row.addWidget(self.btn)
        lay.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setVisible(False)
        lay.addWidget(self.bar)
        self.status = QLabel(_t("All textures are CC0 (public domain). "
                                "polyhaven.com"))
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        close = QPushButton(_t("Close"))
        close.clicked.connect(self.close)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)

    # ---- threads ------------------------------------------------------------
    def _busy_delta(self, d: int) -> None:
        self._busy = max(0, self._busy + d)
        self.bar.setVisible(self._busy > 0)

    def _spawn(self, tag: str, key, fn, *args) -> None:
        self._busy_delta(+1)

        def run() -> None:
            try:
                msg = (tag, key, fn(*args), None)
            except Exception as exc:  # noqa: BLE001
                msg = (tag, key, None, str(exc) or exc.__class__.__name__)
            try:
                self._relay.message.emit(msg)
            except RuntimeError:      # the dialog is gone
                pass

        threading.Thread(target=run, daemon=True).start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.status.setText(_t("Loading the list…"))
            self._spawn("list", None, _http_json, POLY_ASSETS)

    def _on_message(self, msg) -> None:
        tag, key, result, err = msg
        if tag != "thumb":
            self._busy_delta(-1)
        if err:
            if tag == "list":
                self._loaded = False          # offer a retry on next show
            if tag != "thumb":
                self.status.setText(_t("Network error: {err}", err=err))
            return
        if tag == "list":
            self._assets = {k: v for k, v in (result or {}).items()
                            if isinstance(v, dict)}
            cats = sorted({c for v in self._assets.values()
                           for c in (v.get("categories") or [])
                           if isinstance(c, str)}, key=str.lower)
            self.category.blockSignals(True)
            self.category.clear()
            self.category.addItem(_t("All categories"), None)
            for c in cats:
                self.category.addItem(c, c)
            self.category.blockSignals(False)
            self.status.setText(_t("All textures are CC0 (public domain). "
                                   "polyhaven.com"))
            self._refilter()
        elif tag == "thumb":
            self._set_thumb(key, result)
        elif tag == "download":
            name = self._assets.get(key, {}).get("name") or key
            self.status.setText(_t("Downloaded “{name}”", name=name))
            self.panel.rescan(select=result)

    # ---- list ---------------------------------------------------------------
    def _refilter(self, *_a) -> None:
        q = self.search.text().strip().lower()
        cat = self.category.currentData()

        def match(aid: str, info: dict) -> bool:
            if cat is not None and cat not in (info.get("categories") or []):
                return False
            if not q:
                return True
            hay = " ".join([aid, str(info.get("name", ""))]
                           + [str(t) for t in (info.get("tags") or [])])
            return q in hay.lower()

        hits = sorted((aid for aid, info in self._assets.items()
                       if match(aid, info)),
                      key=lambda a: str(self._assets[a].get("name", a)).lower())
        self._ids = hits[:self.MAX_SHOWN]
        self._gen += 1
        self.grid.blockSignals(True)
        self.grid.clear()
        todo = []
        for aid in self._ids:
            info = self._assets[aid]
            item = QListWidgetItem(str(info.get("name") or aid))
            item.setData(Qt.ItemDataRole.UserRole, aid)
            item.setSizeHint(QSize(ICON_PX + 18, ICON_PX + 36))
            if aid in self._thumbs:
                item.setIcon(self._thumbs[aid])
            else:
                todo.append(aid)
            self.grid.addItem(item)
        self.grid.blockSignals(False)
        self.btn.setEnabled(False)
        self.count.setText(_t("{n} shown of {total}", n=len(self._ids),
                              total=len(hits)))
        if todo:
            self._start_thumbs(todo, self._gen)

    def _start_thumbs(self, ids: list, gen: int) -> None:
        def run() -> None:
            for aid in ids:
                if gen != self._gen:
                    return
                try:
                    data = _http_get(POLY_THUMB.format(id=aid),
                                     limit=5 * 1024 * 1024)
                    msg = ("thumb", aid, data, None)
                except Exception:  # noqa: BLE001 — a missing thumb is fine
                    continue
                try:
                    self._relay.message.emit(msg)
                except RuntimeError:
                    return

        threading.Thread(target=run, daemon=True).start()

    def _set_thumb(self, aid: str, data: bytes) -> None:
        pm = QPixmap()
        if not pm.loadFromData(data):
            return
        icon = QIcon(pm.scaled(ICON_PX, ICON_PX,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
        self._thumbs[aid] = icon
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == aid:
                item.setIcon(icon)
                break

    def _current_id(self):
        item = self.grid.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _download(self) -> None:
        aid = self._current_id()
        if aid is None:
            return
        name = str(self._assets.get(aid, {}).get("name") or aid)
        self.status.setText(_t("Downloading “{name}”…", name=name))
        self._spawn("download", aid, download_poly_asset,
                    self.panel._root, aid, name, self.res.currentData())


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def setup(app) -> None:
    panel = TextureLibraryPanel(app)
    dock = app.add_panel(_t("Textures"), panel)
    app.add_menu_action(
        _t("Texture library…"), lambda: app.show_panel(dock), "Ctrl+Shift+T",
        tip=_t("Browse your textures, set their real size and paint with "
               "them."))
