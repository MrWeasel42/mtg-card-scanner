"""VTK off-screen renderer for the sorter: the real CAD meshes (audit/placed), colored by material, with moving
parts (cards, fins, rollers, doors, links, gate) driven by transforms, cutaway planes and text callouts."""
import sys, os, json, math
import numpy as np, trimesh, vtk
from vtk.util import numpy_support as nps
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cad"))
import sorter as S
from sorter import *
HERE = os.path.dirname(os.path.abspath(__file__))
PL = os.path.join(HERE, "placed")
VIS = os.path.join(HERE, "placed_vis")

C = {   # material colors (r, g, b), opacity
    "petg": ((0.80, 0.82, 0.85), 1.0), "black": ((0.13, 0.13, 0.15), 1.0), "green": ((0.25, 0.55, 0.30), 1.0),
    "bin": ((0.93, 0.93, 0.90), 0.55), "alu": ((0.70, 0.72, 0.75), 1.0), "motor": ((0.22, 0.22, 0.25), 1.0),
    "pcb": ((0.10, 0.45, 0.20), 1.0), "belt": ((0.08, 0.08, 0.08), 1.0), "fin": ((0.95, 0.55, 0.10), 1.0),
    "card": ((0.96, 0.94, 0.88), 1.0), "border": ((0.10, 0.10, 0.10), 1.0), "sleeve1": ((0.20, 0.45, 0.95), 0.45),
    "sleeve2": ((0.60, 0.25, 0.85), 0.45), "screen": ((0.05, 0.05, 0.08), 1.0), "accent": ((0.95, 0.35, 0.25), 1.0),
    "led": ((0.35, 0.35, 0.30), 1.0), "glass": ((0.6, 0.8, 1.0), 0.25), "rubber": ((0.15, 0.15, 0.15), 1.0),
    "wire": ((0.85, 0.15, 0.15), 1.0), "gold": ((0.85, 0.65, 0.15), 1.0), "stack": ((0.90, 0.88, 0.80), 1.0),
}
def kind_of(n):
    if n in ("hood", "hood_lid", "sheen_cap", "pod_cover", "bay_cover") or n.startswith(("back_panel",)): return "black"
    if n == "scan_floor": return "green"
    if n.startswith("bin_") and "side" not in n: return "bin"
    if n.startswith(("rail", "shaft_", "idler_stub", "loop_", "psu", "coupler")): return "alu"
    if n.startswith(("nema", "camera", "servo_", "horn_")) and not n.startswith("servo_link"): return "motor"
    if n.startswith(("skr", "hub_", "tof_", "v_", "conv", "home_tcrt", "card_clear")): return "pcb"
    if n.startswith(("idler_b", "idler_f", "drive_")): return "alu"
    if n.startswith("led_channel"): return "led"
    if n.startswith(("beam_",)): return "rubber"
    if n == "screen_block": return "screen"
    if n.startswith(("iec_inlet", "bay_fan", "hall_leads")): return "motor"
    if n.startswith("gate_plate"): return "accent"
    return "petg"

def tri_to_poly(m):
    pts = vtk.vtkPoints(); pts.SetData(nps.numpy_to_vtk(np.asarray(m.vertices, np.float64), deep=True))
    f = np.hstack([np.full((len(m.faces), 1), 3), m.faces]).astype(np.int64).ravel()
    cells = vtk.vtkCellArray(); cells.SetCells(len(m.faces), nps.numpy_to_vtkIdTypeArray(f, deep=True))
    pd = vtk.vtkPolyData(); pd.SetPoints(pts); pd.SetPolys(cells)
    n = vtk.vtkPolyDataNormals(); n.SetInputData(pd); n.SetFeatureAngle(35); n.SplittingOn(); n.Update()
    return n.GetOutput()

def mat4(M):
    v = vtk.vtkMatrix4x4()
    for i in range(4):
        for j in range(4):
            v.SetElement(i, j, float(M[i][j]))
    return v

class Scene:
    def __init__(self, w=1280, h=720, bg=(0.97, 0.97, 0.98)):
        self.ren = vtk.vtkRenderer(); self.ren.SetBackground(*bg); self.ren.SetBackground2(0.82, 0.86, 0.92); self.ren.GradientBackgroundOn()
        self.win = vtk.vtkRenderWindow(); self.win.SetOffScreenRendering(1); self.win.AddRenderer(self.ren); self.win.SetSize(w, h)
        self.win.SetMultiSamples(8)
        self.actors = {}; self.base = {}
        self.ren.AutomaticLightCreationOff()
        for pos, inten in (((1, -1.5, 2), 0.75), ((-1, -0.5, 1.2), 0.35), ((0.5, 1.5, 1.0), 0.35)):
            L = vtk.vtkLight(); L.SetLightTypeToSceneLight(); L.SetPositional(False); L.SetPosition(*pos); L.SetFocalPoint(0, 0, 0)
            L.SetIntensity(inten); self.ren.AddLight(L)
        self.texts = []
        self.planes = vtk.vtkPlaneCollection()

    def add(self, name, mesh, kind=None, M=None, opacity=None, color=None):
        a = vtk.vtkActor(); mp = vtk.vtkPolyDataMapper(); mp.SetInputData(tri_to_poly(mesh)); a.SetMapper(mp)
        col, op = C[kind or kind_of(name)]
        p = a.GetProperty(); p.SetColor(*(color or col)); p.SetOpacity(opacity if opacity is not None else op)
        p.SetSpecular(0.25); p.SetSpecularPower(25); p.SetAmbient(0.12); p.SetDiffuse(0.85)
        if (kind or kind_of(name)) in ("black", "motor", "belt", "screen"):
            p.SetSpecular(0.15)
        bp = vtk.vtkProperty(); bp.DeepCopy(p); bp.SetColor(*[c * 0.55 for c in (color or col)]); a.SetBackfaceProperty(bp)
        if M is not None:
            a.SetUserMatrix(mat4(M))
        self.ren.AddActor(a); self.actors[name] = a
        return a

    def load(self, names=None, skip=()):
        idx = json.load(open(os.path.join(PL, "index.json")))
        for n in idx:
            if names is not None and n not in names: continue
            if n.startswith(("v_",)) or n in skip or any(n.startswith(s) for s in skip): continue
            self.add(n, trimesh.load(os.path.join(PL, n + ".stl")))

    def move(self, name, M):
        self.actors[name].SetUserMatrix(mat4(M))
    def show(self, name, on=True):
        if name in self.actors: self.actors[name].SetVisibility(1 if on else 0)
    def glow(self, name, on, col=(1.0, 0.97, 0.85)):
        p = self.actors[name].GetProperty()
        if on: p.SetAmbient(1.0); p.SetAmbientColor(*col); p.SetColor(*col)
        else: p.SetAmbient(0.12); p.SetColor(*C["led"][0])

    def clip(self, names, origin, normal):
        """Cut these actors with a plane (keeps the side the normal points to)."""
        pl = vtk.vtkPlane(); pl.SetOrigin(*origin); pl.SetNormal(*normal)
        for n in names:
            if n in self.actors:
                self.actors[n].GetMapper().AddClippingPlane(pl)
        return pl
    def unclip(self, names=None):
        for n, a in self.actors.items():
            if names is None or n in names:
                a.GetMapper().RemoveAllClippingPlanes()

    def camera(self, pos, focal, up=(0, 0, 1), angle=30.0):
        c = self.ren.GetActiveCamera(); c.SetPosition(*pos); c.SetFocalPoint(*focal); c.SetViewUp(*up); c.SetViewAngle(angle)
        self.ren.ResetCameraClippingRange()

    def text(self, s, x, y, size=22, color=(0.1, 0.1, 0.12), bold=False, bg=None, just="left"):
        t = vtk.vtkTextActor(); t.SetInput(s); tp = t.GetTextProperty(); tp.SetFontSize(size); tp.SetColor(*color); tp.SetBold(bold)
        tp.SetFontFamilyToArial()
        if just == "center": tp.SetJustificationToCentered()
        if bg is not None:
            tp.SetBackgroundColor(*bg); tp.SetBackgroundOpacity(0.85); tp.SetFrame(0)
        t.SetDisplayPosition(int(x), int(y)); self.ren.AddActor2D(t); self.texts.append(t)
        return t
    def callout(self, s, p3, dx=60, dy=40, size=20, color=(0.05, 0.05, 0.1)):
        c = vtk.vtkCaptionActor2D(); c.SetCaption(s); c.SetAttachmentPoint(*p3); c.BorderOff(); c.LeaderOn(); c.ThreeDimensionalLeaderOff()
        c.GetCaptionTextProperty().SetFontSize(size); c.GetCaptionTextProperty().SetColor(*color); c.GetCaptionTextProperty().SetBold(True)
        c.GetCaptionTextProperty().SetShadow(False); c.GetCaptionTextProperty().SetFontFamilyToArial(); c.GetCaptionTextProperty().ItalicOff()
        c.GetCaptionTextProperty().SetBackgroundColor(1, 1, 1); c.GetCaptionTextProperty().SetBackgroundOpacity(0.8)
        c.GetProperty().SetColor(0.85, 0.2, 0.1); c.GetProperty().SetLineWidth(2)
        c.SetPadding(4)
        w = max(len(l) for l in s.split("\n")) * size * 0.62; h = size * 1.45 * len(s.split("\n"))
        c.SetPosition(dx, dy); c.SetWidth(w / self.win.GetSize()[0]); c.SetHeight(h / self.win.GetSize()[1])
        c.SetPosition(dx, dy)                       # label offset (pixels) from the point it points at: it follows the point
        c.GetPosition2Coordinate().SetCoordinateSystemToDisplay(); c.GetPosition2Coordinate().SetValue(w, h)
        c.SetPosition2(w, h)
        self.ren.AddActor2D(c); self.texts.append(c)
        return c
    def clear_text(self):
        for t in self.texts: self.ren.RemoveActor2D(t)
        self.texts = []

    def png(self, path):
        self.ren.ResetCameraClippingRange()
        self.win.Render()
        f = vtk.vtkWindowToImageFilter(); f.SetInput(self.win); f.ReadFrontBufferOff(); f.Update()
        w = vtk.vtkPNGWriter(); w.SetFileName(path); w.SetInputConnection(f.GetOutputPort()); w.Write()
    def frame_bytes(self):
        self.ren.ResetCameraClippingRange(); self.win.Render()
        f = vtk.vtkWindowToImageFilter(); f.SetInput(self.win); f.ReadFrontBufferOff(); f.Update()
        im = f.GetOutput(); w, h, _ = im.GetDimensions()
        a = nps.vtk_to_numpy(im.GetPointData().GetScalars()).reshape(h, w, -1)[::-1, :, :3]
        return np.ascontiguousarray(a).tobytes()

# ---------------------------------------------------------------- moving machinery
LOOP = 2 * (END_SHAFT_X - FIN_START_X) + 2 * math.pi * PUL_R
RB = PUL_Z - BELT_BACK_LOW          # pulley axis to the belt's back

def roty(a, cx, cz):
    return trimesh.transformations.rotation_matrix(a, [0, 1, 0], [cx, 0, cz])
def fin_pose(s):
    """Belt position s (mm from the start idler's bottom, along the loop, + = direction of travel) -> 4x4 for a fin
    built in its bottom-run frame at x 0."""
    s = s % LOOP
    run = END_SHAFT_X - FIN_START_X
    arc = math.pi * RB
    T = np.eye(4)
    if s < run:
        T[0, 3] = FIN_START_X + s; return T
    s -= run
    if s < arc:
        T[0, 3] = END_SHAFT_X; return roty(-s / RB, END_SHAFT_X, PUL_Z) @ T
    s -= arc
    if s < run:
        T[0, 3] = END_SHAFT_X; return trimesh.transformations.translation_matrix((-s, 0, 0)) @ roty(-math.pi, END_SHAFT_X, PUL_Z) @ T
    s -= run
    s = min(s, arc)
    T[0, 3] = FIN_START_X
    return roty(-math.pi - s / RB, FIN_START_X, PUL_Z) @ T

def fin_meshes():
    yc = (BELT_Y0 + BELT_Y1) / 2
    out = {}
    for sg in (1, -1):
        f = fin() if sg > 0 else fin().mirror("XZ")
        v, t = f.val().tessellate(0.02, 0.2)
        m = trimesh.Trimesh([(p.x, p.y, p.z) for p in v], t)
        m.apply_translation((-5.0, sg * yc, BELT_BACK_LOW))     # pushing face at x 0
        out[sg] = m
    return out

def belt_meshes():
    """The two belts as thin loops (straight runs + half rings round the pulleys)."""
    out = []
    for sg in (1, -1):
        y0, y1 = sorted((sg * BELT_Y0, sg * BELT_Y1))
        lo = trimesh.creation.box(extents=(END_SHAFT_X - FIN_START_X, y1 - y0, 1.38)); lo.apply_translation(((FIN_START_X + END_SHAFT_X) / 2, (y0 + y1) / 2, BELT_BACK_LOW + 0.69))
        hi = lo.copy(); hi.apply_translation((0, 0, 2 * (PUL_Z - BELT_BACK_LOW) - 1.38))
        out += [lo, hi]
        for xc, a0 in ((END_SHAFT_X, -math.pi / 2), (FIN_START_X, math.pi / 2)):
            ring = trimesh.creation.annulus(r_min=RB - 1.38, r_max=RB, height=y1 - y0, sections=48)
            ring.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0]))
            ring.apply_translation((xc, (y0 + y1) / 2, PUL_Z))
            sl = trimesh.intersections.slice_mesh_plane(ring, [1 if xc > 500 else -1, 0, 0], [xc, 0, 0], cap=True)
            out.append(sl)
    return trimesh.util.concatenate(out)

def card_parts(kind):
    import sim
    L, W, t, _, _ = sim.CARDS[kind]
    core = trimesh.creation.box(extents=(88.0, 63.0, 0.31))                    # black border
    art = trimesh.creation.box(extents=(44.0, 52.0, 0.04)); art.apply_translation((10.0, 0, 0.17))
    tb = trimesh.creation.box(extents=(26.0, 52.0, 0.04)); tb.apply_translation((-25.0, 0, 0.17))
    parts = [("border", core), ("accent", art), ("card", tb)]
    if kind != "raw":
        sl = trimesh.creation.box(extents=(L, W, t)); parts.append(("sleeve1" if kind == "single" else "sleeve2", sl))
    return parts
