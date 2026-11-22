import trimesh, json, numpy as np, itertools, sys
import manifold3d as m3
idx = json.load(open("placed/index.json"))
M = {}
for k in idx:
    t = trimesh.load(f"placed/{k}.stl")
    M[k] = t
def man(t):
    return m3.Manifold(m3.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))
MM = {k: man(t) for k, t in M.items()}
bad = [k for k,v in MM.items() if v.status() != m3.Error.NoError or v.volume() <= 0]
print("non-manifold:", bad)
res = []
keys = list(M)
for a, b in itertools.combinations(keys, 2):
    ba, bb = M[a].bounds, M[b].bounds
    if np.any(ba[1] < bb[0] - 0.01) or np.any(bb[1] < ba[0] - 0.01):
        continue
    v = (MM[a] ^ MM[b]).volume()
    if v > 0.05:
        bx = (MM[a] ^ MM[b]).bounding_box()
        res.append((round(v, 2), a, b, [round(x, 1) for x in bx]))
res.sort(reverse=True)
for r in res: print(r)
json.dump(res, open("pairs.json", "w"))
