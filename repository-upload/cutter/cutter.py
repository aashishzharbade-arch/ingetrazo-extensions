# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Cutter contributors.
"""Cutter — slice the model with a line you draw, or at a section plane.

Free software (GPL-3.0-or-later), written from scratch for IngeTrazo.

Features:
* Works on loose faces as well as **Groups and Components** (including nested).
* **SketchUp-style draggable and dockable toolbar** with intuitive icons.
* Three entries in the **Extensions** menu:
  * **Cutter: Slice** — click two points to slice through the model.
  * **Cutter: Slice & Remove** — slice and delete everything on the right side.
  * **Cutter: Slice at Section Plane** — cut at the active section plane and
    delete the hidden side.

What gets cut:
* If loose faces or groups/components are selected, only those selected items
  are cut.
* If nothing is selected, the cut operates on loose faces and all top-level
  groups and components in the context.

Every cut is ONE single undo step.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QMatrix4x4,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QVector3D,
)
try:
    from PySide6.QtGui import QAction
except ImportError:
    from PySide6.QtWidgets import QAction  # fallback for older Qt bindings

from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar

from tools.base import Tool, ToolContext

#: Plane-side tolerance, in metres: geometry closer than this to the plane
#: counts as lying ON it and is never removed.
_EPS = 1e-6


# ---- Geometry: pure functions ------------------------------------------------

def plane_from_rays(o1, d1, o2, d2):
    """``(point, normal)`` of the plane swept by two camera rays.

    Perspective: both rays start at the eye, so the plane holds the eye and
    both directions. Parallel projection: the rays are parallel and the
    plane holds both, running along the view direction.
    """
    o1, d1, o2, d2 = (QVector3D(v) for v in (o1, d1, o2, d2))
    if (d1 - d2).length() < 1e-7:                       # parallel projection
        n = QVector3D.crossProduct(o2 - o1, d1)
    else:                                               # perspective
        n = QVector3D.crossProduct(d1, d2)
    if n.length() < 1e-9:
        return None
    return o1, n.normalized()


def side_of(point, normal, p) -> float:
    """Signed distance of ``p`` from the plane; > 0 on the normal's side."""
    return QVector3D.dotProduct(normal, p - point)


def knife_polygon(point, normal, lo, hi):
    """A flat square on the plane, big enough to cover the box ``lo..hi``."""
    from core.intersect import _Poly
    from core.triangulate import plane_axes
    n = QVector3D(normal).normalized()
    lo, hi = QVector3D(*lo), QVector3D(*hi)
    centre = (lo + hi) * 0.5
    centre = centre - n * QVector3D.dotProduct(n, centre - point)
    half = (hi - lo).length() + 1.0
    u, v = plane_axes(n)
    ring = [centre + (u * -half) + (v * -half),
            centre + (u * half) + (v * -half),
            centre + (u * half) + (v * half),
            centre + (u * -half) + (v * half)]
    return _Poly([ring], n)


# ---- Groups & Components support helpers -------------------------------------

def _is_group_or_component(obj) -> bool:
    """Check if an entity is a Group or Component instance."""
    if obj is None:
        return False
    name = type(obj).__name__.lower()
    if any(k in name for k in ("group", "component", "instance")):
        return True
    if getattr(obj, "is_group", False) or getattr(obj, "is_component", False):
        return True
    if hasattr(obj, "mesh") and not hasattr(obj, "active_section"):
        if name not in ("face", "edge", "vertex", "scene", "model"):
            return True
    if hasattr(obj, "definition") and hasattr(getattr(obj, "definition"), "mesh"):
        return True
    return False


def _get_entity_mesh(entity):
    """Return the underlying mesh of an entity or group/component."""
    if hasattr(entity, "mesh") and entity.mesh is not None:
        return entity.mesh
    defn = getattr(entity, "definition", None)
    if defn is not None and hasattr(defn, "mesh"):
        return defn.mesh
    return None


def _get_child_groups(entity) -> list:
    """Recursively retrieve nested child groups/components."""
    children = []
    for attr in ("groups", "children", "instances", "entities"):
        val = getattr(entity, attr, None)
        if isinstance(val, (list, tuple, set)):
            for item in val:
                if _is_group_or_component(item):
                    children.append(item)
    defn = getattr(entity, "definition", None)
    if defn is not None:
        for attr in ("groups", "children", "instances", "entities"):
            val = getattr(defn, attr, None)
            if isinstance(val, (list, tuple, set)):
                for item in val:
                    if _is_group_or_component(item):
                        children.append(item)
    return children


def _get_scene_groups(scene) -> list:
    """Find all top-level groups and component instances in the scene."""
    groups = []
    for attr in ("groups", "instances", "components", "entities"):
        val = getattr(scene, attr, None)
        if isinstance(val, (list, tuple, set)):
            for item in val:
                if _is_group_or_component(item):
                    groups.append(item)
    return groups


def _get_matrix4x4(entity) -> QMatrix4x4:
    """Extract transformation matrix from entity as QMatrix4x4."""
    tf = None
    for attr in ("transform", "transformation", "matrix", "world_matrix", "local_matrix"):
        val = getattr(entity, attr, None)
        if val is not None:
            tf = val
            break
    if tf is None:
        return QMatrix4x4()
    if isinstance(tf, QMatrix4x4):
        return QMatrix4x4(tf)
    if hasattr(tf, "to_qmatrix4x4") and callable(tf.to_qmatrix4x4):
        return tf.to_qmatrix4x4()
    if hasattr(tf, "matrix"):
        tf = tf.matrix
    try:
        flat = [float(x) for row in tf for x in (row if isinstance(row, (list, tuple)) else [row])]
        if len(flat) == 16:
            return QMatrix4x4(*flat)
    except Exception:
        pass
    return QMatrix4x4()


def plane_to_local(point: QVector3D, normal: QVector3D, matrix: QMatrix4x4):
    """Transform world cutting plane (point, normal) into entity local coordinates."""
    if matrix.isIdentity():
        return QVector3D(point), QVector3D(normal)
    inv, invertible = matrix.inverted()
    if not invertible:
        return QVector3D(point), QVector3D(normal)
    local_pt = inv.map(point)
    local_norm = inv.mapVector(normal).normalized()
    if local_norm.length() < 1e-6:
        local_norm = normal
    return local_pt, local_norm


def _get_mesh_vertices(mesh) -> list[QVector3D]:
    """Retrieve all vertex positions of a mesh."""
    raw = getattr(mesh, "vertices", None)
    if raw is None and hasattr(mesh, "faces"):
        raw = []
        for f in mesh.faces:
            raw.extend(getattr(f, "vertices", []))
    if not raw:
        return []
    res = []
    for item in raw:
        if isinstance(item, QVector3D):
            res.append(item)
        elif hasattr(item, "pos"):
            res.append(QVector3D(item.pos))
        elif hasattr(item, "x") and hasattr(item, "y") and hasattr(item, "z"):
            res.append(QVector3D(item.x, item.y, item.z))
    return res


def _remove_group_from_scene(scene, group, parent=None) -> bool:
    """Erase a group or component from its parent container or scene."""
    if parent is not None:
        for attr in ("groups", "children", "instances", "entities"):
            container = getattr(parent, attr, None)
            if isinstance(container, list) and group in container:
                container.remove(group)
                return True
            if isinstance(container, set) and group in container:
                container.discard(group)
                return True

    for method in ("remove_group", "delete_group", "remove_instance", "remove_entity", "erase"):
        fn = getattr(scene, method, None)
        if callable(fn):
            try:
                fn(group)
                return True
            except Exception:
                pass

    for attr in ("groups", "instances", "entities", "components"):
        container = getattr(scene, attr, None)
        if isinstance(container, list) and group in container:
            container.remove(group)
            return True
        if isinstance(container, set) and group in container:
            container.discard(group)
            return True

    try:
        from core.history import EraseSelectionCommand
        EraseSelectionCommand([group], []).do(scene)
        return True
    except Exception:
        pass
    return False


class MeshContext:
    """Adapter presenting any target Mesh as an editable context for edits."""
    def __init__(self, scene, mesh):
        self._scene = scene
        self.mesh = mesh
        self.selection = []
        self.history = getattr(scene, "history", None)

    def __getattr__(self, name):
        return getattr(self._scene, name)


# ---- Face and Polygon Intersections ------------------------------------------

def cut_segments_for_faces(faces, point, normal) -> list:
    """Compute intersecting line segments for given faces and plane."""
    from core import intersect as X
    polys = [p for p in (X.world_polys(f) for f in faces) if p is not None]
    if not polys:
        return []
    lo = [min(p.lo[i] for p in polys) for i in range(3)]
    hi = [max(p.hi[i] for p in polys) for i in range(3)]
    knife = knife_polygon(point, normal, lo, hi)
    return X.intersect(polys, [knife])


def cut_segments(scene, point, normal) -> list:
    """The edges a cut at the plane would add on loose faces."""
    from core.mesh import Face
    chosen = [e for e in getattr(scene, "selection", []) if isinstance(e, Face)]
    faces = chosen or list(getattr(scene.mesh, "faces", []))
    return cut_segments_for_faces(faces, point, normal)


def _loops(segments, tol: float = 1e-6) -> list:
    """Chain cut segments into closed loops of points."""
    def key(q):
        return (round(q.x() / tol), round(q.y() / tol), round(q.z() / tol))
    points, nxt = {}, {}
    for a, b in segments:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        points[ka], points[kb] = QVector3D(a), QVector3D(b)
        nxt.setdefault(ka, set()).add(kb)
        nxt.setdefault(kb, set()).add(ka)
    loops, used = [], set()
    for start in list(nxt):
        for first in list(nxt[start]):
            if (start, first) in used:
                continue
            chain, prev, cur = [start], start, first
            used.add((start, first))
            used.add((first, start))
            while cur != start:
                chain.append(cur)
                options = [k for k in nxt[cur]
                           if k != prev and (cur, k) not in used]
                if not options:
                    chain = None
                    break
                used.add((cur, options[0]))
                used.add((options[0], cur))
                prev, cur = cur, options[0]
            if chain and len(chain) >= 3:
                loops.append([points[k] for k in chain])
    return loops


def _area2d(ring2d) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                     in zip(ring2d, ring2d[1:] + ring2d[:1]))


def _inside2d(pt, ring2d) -> bool:
    x, y = pt
    hit = False
    for (x0, y0), (x1, y1) in zip(ring2d, ring2d[1:] + ring2d[:1]):
        if (y0 > y) != (y1 > y) and \
                x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            hit = not hit
    return hit


def cap_faces(mesh, segments, normal, facing) -> int:
    """Add a face over every closed loop the cut made. Returns faces added."""
    from core.triangulate import plane_axes
    from tools.base import face_the_plane
    loops = _loops(segments)
    if not loops:
        return 0
    u, v = plane_axes(normal)
    flat = [[(QVector3D.dotProduct(q, u), QVector3D.dotProduct(q, v))
             for q in ring] for ring in loops]
    order = sorted(range(len(loops)), key=lambda i: -abs(_area2d(flat[i])))
    owner = {}
    for pos, i in enumerate(order):
        for j in order[:pos][::-1]:
            if _inside2d(flat[i][0], flat[j]) and owner.get(j) is None:
                owner[i] = j
                break
    added = 0
    for i in order:
        if i in owner:
            continue
        holes = [[QVector3D(q) for q in loops[k]]
                 for k, o in owner.items() if o == i]
        outer = face_the_plane(loops[i], facing)
        try:
            mesh.add_face(outer, holes or None)
            added += 1
        except Exception:                       # noqa: BLE001
            continue
    return added


def _remove_mesh_side(ctx, mesh, point, normal, sign: float) -> int:
    """Erase geometry strictly on one side of the plane from the mesh."""
    from core.history import EraseSelectionCommand
    faces = [f for f in mesh.faces
             if sign * side_of(point, normal, f.centroid()) > _EPS]
    edges = [e for e in mesh.edges
             if sign * side_of(point, normal, QVector3D(e.a)) > -_EPS
             and sign * side_of(point, normal, QVector3D(e.b)) > -_EPS
             and sign * side_of(point, normal,
                                (QVector3D(e.a) + QVector3D(e.b)) * 0.5) > _EPS]
    if faces or edges:
        try:
            EraseSelectionCommand(edges, faces).do(ctx)
        except Exception:
            for f in faces:
                for rem in ("remove_face", "delete_face"):
                    fn = getattr(mesh, rem, None)
                    if callable(fn):
                        fn(f)
                        break
            for e in edges:
                for rem in ("remove_edge", "delete_edge"):
                    fn = getattr(mesh, rem, None)
                    if callable(fn):
                        fn(e)
                        break
    return len(faces)


def _process_group_cut(scene, group, world_pt, world_norm, remove_sign, cap,
                       parent_mat=QMatrix4x4()) -> tuple[int, int, int, int]:
    """Recursively slice/remove/cap a group and its children.

    Returns (cut_edges, removed_faces, removed_groups, caps).
    """
    from core.edits import build_add_edges
    curr_mat = parent_mat * _get_matrix4x4(group)
    pt_loc, norm_loc = plane_to_local(world_pt, world_norm, curr_mat)
    mesh = _get_entity_mesh(group)

    edges_count, rem_faces, rem_groups, cap_count = 0, 0, 0, 0

    if mesh is not None and getattr(mesh, "faces", None):
        verts = _get_mesh_vertices(mesh)
        if verts and remove_sign != 0.0:
            all_removed = all(remove_sign * side_of(pt_loc, norm_loc, v) > _EPS for v in verts)
            if all_removed:
                if _remove_group_from_scene(scene, group):
                    return 0, len(mesh.faces), 1, 0

        all_retained = bool(verts) and all(
            remove_sign * side_of(pt_loc, norm_loc, v) < -_EPS for v in verts
        ) if remove_sign != 0.0 else False

        if not all_retained:
            segments = cut_segments_for_faces(list(mesh.faces), pt_loc, norm_loc)
            if segments:
                ctx = MeshContext(scene, mesh)
                build_add_edges(ctx, segments, detect_faces=True).do(ctx)
                edges_count += len(segments)
                if cap:
                    facing = norm_loc * (remove_sign or 1.0)
                    cap_count += cap_faces(mesh, segments, norm_loc, facing)

            if remove_sign != 0.0:
                ctx = MeshContext(scene, mesh)
                rem_faces += _remove_mesh_side(ctx, mesh, pt_loc, norm_loc, remove_sign)

    # Process nested child groups/components
    for child in _get_child_groups(group):
        c_edges, c_rem_f, c_rem_g, c_caps = _process_group_cut(
            scene, child, world_pt, world_norm, remove_sign, cap, curr_mat
        )
        edges_count += c_edges
        rem_faces += c_rem_f
        rem_groups += c_rem_g
        cap_count += c_caps

    return edges_count, rem_faces, rem_groups, cap_count


def slice_model(viewport, point, normal, remove_sign: float = 0.0,
                cap: bool = True) -> str:
    """Cut at the plane (loose faces + groups/components) as ONE undo step."""
    from core.edits import build_add_edges
    from core.history import SnapshotImport
    from core.mesh import Face

    scene = viewport.scene
    sel = getattr(scene, "selection", []) or []
    sel_faces = [e for e in sel if isinstance(e, Face)]
    sel_groups = [e for e in sel if _is_group_or_component(e)]

    # Determine targets: selected faces/groups, or context default
    if sel_faces or sel_groups:
        target_loose = sel_faces
        target_groups = sel_groups
    else:
        target_loose = list(getattr(scene.mesh, "faces", [])) if hasattr(scene, "mesh") else []
        target_groups = _get_scene_groups(scene)

    stats = {"cut_edges": 0, "faces_removed": 0, "groups_removed": 0, "caps": 0}

    def mutate(sc):
        # 1. Slice loose geometry in scene.mesh
        if target_loose and hasattr(sc, "mesh"):
            segments = cut_segments_for_faces(target_loose, point, normal)
            if segments:
                build_add_edges(sc, segments, detect_faces=True).do(sc)
                stats["cut_edges"] += len(segments)
                if cap:
                    facing = normal * (remove_sign or 1.0)
                    stats["caps"] += cap_faces(sc.mesh, segments, normal, facing)
            if remove_sign != 0.0:
                stats["faces_removed"] += _remove_mesh_side(sc, sc.mesh, point, normal, remove_sign)

        # 2. Slice targeted groups and components
        for g in target_groups:
            c_edges, c_rem_f, c_rem_g, c_caps = _process_group_cut(
                sc, g, point, normal, remove_sign, cap
            )
            stats["cut_edges"] += c_edges
            stats["faces_removed"] += c_rem_f
            stats["groups_removed"] += c_rem_g
            stats["caps"] += c_caps

    viewport.history.execute(SnapshotImport(mutate))
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()

    if remove_sign:
        g_info = f", {stats['groups_removed']} group(s) deleted" if stats["groups_removed"] else ""
        return (f"Cutter: {stats['cut_edges']} cut edges, "
                f"{stats['faces_removed']} faces removed{g_info}, {stats['caps']} cap(s)")
    return f"Cutter: {stats['cut_edges']} cut edges added across model and groups"


def slice_at_section(viewport) -> str:
    """Cut at the active section plane and delete its hidden side."""
    sp = viewport.scene.active_section()
    if sp is None:
        return "Cutter: there is no active section plane"
    return slice_model(viewport, sp.point, sp.normal, remove_sign=1.0)


# ---- Interactive Two-Click Tool ----------------------------------------------

class _LineCutTool(Tool):
    """Two clicks draw the cut line across screen view."""

    name = "Cutter"
    description = "Click two points to slice through the model."

    def __init__(self, mode: str) -> None:
        self.mode = mode                    # "slice" | "remove"
        self._first = None                  # (world, pixel)
        self._hover = None

    def on_activate(self, viewport) -> None:
        self._first = self._hover = None
        viewport.flash_status(
            "Cutter: click the start of the cut line (Esc to cancel)", 4000)

    def on_deactivate(self, viewport) -> None:
        self._first = self._hover = None

    def on_cancel(self, viewport) -> None:
        self._first = self._hover = None

    @staticmethod
    def _pixel(ctx: ToolContext):
        vp = ctx.viewport
        project = getattr(vp, "_world_to_pixel", None)
        px = project(ctx.world) if callable(project) else None
        if px is None:
            return (ctx.screen.x(), ctx.screen.y())
        return px

    def on_hover(self, ctx: ToolContext) -> None:
        self._hover = QVector3D(ctx.world)

    def on_click(self, ctx: ToolContext) -> None:
        vp = ctx.viewport
        here = (QVector3D(ctx.world), self._pixel(ctx))
        if self._first is None:
            self._first = here
            vp.flash_status("Cutter: click the end of the cut line", 4000)
            return
        (_w1, p1), (_w2, p2) = self._first, here
        self._first = self._hover = None
        if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) < 3:
            vp.flash_status("Cutter: the line is too short")
            return
        o1, d1 = vp._pixel_to_ray(*p1)
        o2, d2 = vp._pixel_to_ray(*p2)
        if o1 is None or o2 is None:
            return
        plane = plane_from_rays(o1, d1, o2, d2)
        if plane is None:
            vp.flash_status("Cutter: the line does not define a plane")
            return
        point, normal = plane
        sign = 0.0
        if self.mode == "remove":
            sign = self._right_hand_sign(vp, p1, p2, point, normal)
        vp.flash_status(slice_model(vp, point, normal, sign), 4000)

    @staticmethod
    def _right_hand_sign(vp, p1, p2, point, normal) -> float:
        """+1 when normal points to the right of line, else -1."""
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        qx, qy = mx + 40 * (-dy) / length, my + 40 * dx / length
        o, d = vp._pixel_to_ray(qx, qy)
        if o is None:
            return 1.0
        s = (QVector3D.dotProduct(normal, o - point)
             + QVector3D.dotProduct(normal, d))
        return 1.0 if s > 0 else -1.0

    def rubber_band_lines(self):
        if self._first is None or self._hover is None:
            return []
        return [(self._first[0], self._hover)]


# ---- Toolbar & SketchUp-Style UI ---------------------------------------------

def _create_cutter_icon(action_type: str) -> QIcon:
    """Generate clean, SketchUp-style icons programmatically."""
    pix = QPixmap(48, 48)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if action_type == "slice":
        # Draw 3D cube
        top = QPolygonF([QPointF(24, 7), QPointF(39, 15), QPointF(24, 23), QPointF(9, 15)])
        left = QPolygonF([QPointF(9, 15), QPointF(24, 23), QPointF(24, 41), QPointF(9, 33)])
        right = QPolygonF([QPointF(24, 23), QPointF(39, 15), QPointF(39, 33), QPointF(24, 41)])
        p.setPen(QPen(QColor(40, 50, 60), 1.8))
        p.setBrush(QBrush(QColor(235, 240, 245)))
        p.drawPolygon(top)
        p.setBrush(QBrush(QColor(180, 195, 210)))
        p.drawPolygon(left)
        p.setBrush(QBrush(QColor(140, 160, 180)))
        p.drawPolygon(right)
        # Cutting line (orange/red blade line)
        pen = QPen(QColor(230, 60, 40), 2.8)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(5, 7), QPointF(43, 41))

    elif action_type == "remove":
        # Sliced box with retained left side & removed right side
        left = QPolygonF([QPointF(9, 15), QPointF(24, 23), QPointF(24, 41), QPointF(9, 33)])
        top_half = QPolygonF([QPointF(24, 7), QPointF(24, 23), QPointF(9, 15)])
        p.setPen(QPen(QColor(40, 50, 60), 1.8))
        p.setBrush(QBrush(QColor(90, 165, 230)))
        p.drawPolygon(top_half)
        p.setBrush(QBrush(QColor(60, 130, 200)))
        p.drawPolygon(left)
        # Removed ghost side
        p.setPen(QPen(QColor(210, 80, 80, 180), 1.6, Qt.PenStyle.DotLine))
        p.setBrush(QBrush(QColor(240, 100, 100, 40)))
        ghost = QPolygonF([QPointF(24, 7), QPointF(39, 15), QPointF(39, 33), QPointF(24, 41), QPointF(24, 23)])
        p.drawPolygon(ghost)
        # Red X deletion badge
        p.setPen(QPen(QColor(220, 30, 30), 2.5))
        p.drawLine(QPointF(29, 21), QPointF(35, 27))
        p.drawLine(QPointF(35, 21), QPointF(29, 27))

    elif action_type == "section":
        # Cube with an active amber cutting section plane
        p.setPen(QPen(QColor(60, 70, 80), 1.6))
        p.setBrush(QBrush(QColor(200, 215, 225)))
        cube = QPolygonF([QPointF(14, 11), QPointF(34, 11), QPointF(34, 37), QPointF(14, 37)])
        p.drawPolygon(cube)
        # Amber section plane
        p.setPen(QPen(QColor(235, 130, 20), 2.2))
        p.setBrush(QBrush(QColor(255, 170, 0, 95)))
        sec = QPolygonF([QPointF(6, 17), QPointF(42, 17), QPointF(38, 31), QPointF(2, 31)])
        p.drawPolygon(sec)
        # Direction arrow
        p.drawLine(QPointF(22, 24), QPointF(22, 34))
        p.drawLine(QPointF(19, 31), QPointF(22, 34))
        p.drawLine(QPointF(25, 31), QPointF(22, 34))

    p.end()
    return QIcon(pix)


def _find_main_window() -> QMainWindow | None:
    """Find the active top-level QMainWindow for toolbar docking."""
    app = QApplication.instance()
    if not app:
        return None
    for w in app.topLevelWidgets():
        if isinstance(w, QMainWindow):
            return w
    w = app.activeWindow()
    if isinstance(w, QMainWindow):
        return w
    for w in app.topLevelWidgets():
        if hasattr(w, "addToolBar"):
            return w
    return None


def _get_active_viewport(window=None):
    """Retrieve the current 3D viewport."""
    if window is not None:
        for attr in ("viewport", "active_viewport", "view", "canvas", "gl_widget"):
            vp = getattr(window, attr, None)
            if vp is not None and hasattr(vp, "scene"):
                return vp
        for child in window.findChildren(object):
            if hasattr(child, "scene") and hasattr(child, "set_active_tool"):
                return child
    app = QApplication.instance()
    if app:
        for w in app.topLevelWidgets():
            for attr in ("viewport", "active_viewport", "view", "canvas", "gl_widget"):
                vp = getattr(w, attr, None)
                if vp is not None and hasattr(vp, "scene"):
                    return vp
            for child in w.findChildren(object):
                if hasattr(child, "scene") and hasattr(child, "set_active_tool"):
                    return child
    return None


def create_cutter_toolbar(main_window=None) -> QToolBar | None:
    """Create and dock a SketchUp-style movable/dockable Cutter toolbar."""
    if main_window is None:
        main_window = _find_main_window()
    if main_window is None or not hasattr(main_window, "addToolBar"):
        return None

    existing = main_window.findChild(QToolBar, "CutterToolBar")
    if existing is not None:
        return existing

    toolbar = QToolBar("Cutter", main_window)
    toolbar.setObjectName("CutterToolBar")
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(Qt.ToolBarArea.AllToolBarAreas)
    toolbar.setIconSize(QSize(24, 24))

    # Action 1: Slice
    act_slice = QAction(_create_cutter_icon("slice"), "Cutter: Slice", toolbar)
    act_slice.setToolTip("Cutter: Slice (click two points to slice through model & groups)")
    def on_slice():
        vp = _get_active_viewport(main_window)
        if vp:
            vp.set_active_tool(_LineCutTool("slice"))
    act_slice.triggered.connect(on_slice)
    toolbar.addAction(act_slice)

    # Action 2: Slice & Remove
    act_remove = QAction(_create_cutter_icon("remove"), "Cutter: Slice & Remove", toolbar)
    act_remove.setToolTip("Cutter: Slice & Remove (slice and delete everything on right side)")
    def on_remove():
        vp = _get_active_viewport(main_window)
        if vp:
            vp.set_active_tool(_LineCutTool("remove"))
    act_remove.triggered.connect(on_remove)
    toolbar.addAction(act_remove)

    # Action 3: Slice at Section Plane
    act_sec = QAction(_create_cutter_icon("section"), "Cutter: Slice at Section", toolbar)
    act_sec.setToolTip("Cutter: Slice at Section Plane (cut at active section plane & delete hidden side)")
    def on_sec():
        vp = _get_active_viewport(main_window)
        if vp:
            vp.flash_status(slice_at_section(vp), 4000)
    act_sec.triggered.connect(on_sec)
    toolbar.addAction(act_sec)

    main_window.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
    return toolbar


# Ensure toolbar is mounted on application startup
QTimer.singleShot(250, lambda: create_cutter_toolbar())


# ---- Extensions Menu Entries -------------------------------------------------

class CutterSlice(Tool):
    name = "Cutter: Slice"
    description = "Draw a line to slice the faces, groups, and components you are editing."
    shortcut = None
    menu_order = 20

    def on_activate(self, viewport) -> None:
        create_cutter_toolbar(viewport.window() if hasattr(viewport, "window") else None)
        viewport.set_active_tool(_LineCutTool("slice"))

    def on_deactivate(self, viewport) -> None:
        pass


class CutterSliceRemove(Tool):
    name = "Cutter: Slice & Remove"
    description = ("Draw a line to slice, and delete everything on the "
                   "right-hand side of it (supports groups & components).")
    shortcut = None
    menu_order = 21

    def on_activate(self, viewport) -> None:
        create_cutter_toolbar(viewport.window() if hasattr(viewport, "window") else None)
        viewport.set_active_tool(_LineCutTool("remove"))

    def on_deactivate(self, viewport) -> None:
        pass


class CutterAtSection(Tool):
    name = "Cutter: Slice at Section Plane"
    description = ("Cut at the active section plane and delete its hidden "
                   "side across loose faces and groups.")
    shortcut = None
    menu_order = 22

    def on_activate(self, viewport) -> None:
        create_cutter_toolbar(viewport.window() if hasattr(viewport, "window") else None)
        viewport.flash_status(slice_at_section(viewport), 4000)

    def on_deactivate(self, viewport) -> None:
        pass