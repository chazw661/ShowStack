# ShowStack cable linker for Vectorworks (v0.3 - writes fields by default)
#
# MAIN RUN  = a cable with one end at an amp rack.
#   CableObject.UserField_1 <- fan-out at the other end (ShowStack name)
#   CableObject.UserField_2 <- rack name (EntEquipUniversal "Unit Number", etc.)
#   CableObject.UserField_3 <- total length ft (Length + Spare + Swag)
# EXTENSION = a cable with no rack at either end, starting at a fan-out where a main run ends.
#   CableObject.Loom_ID     <- the main run's label (CableRun_ID)  -> worksheet column "Extension Of"
#   CableObject.UserField_3 <- total length ft
# Fields are only overwritten when a match is found, so manual entries survive.
# Writes a report to ~/Desktop/showstack_link_report.txt
#
# DRY_RUN = True  : reports only, changes nothing
# DRY_RUN = False : also writes the fields on each cable

import vs
import os
import math

DRY_RUN = False
TOL = 36.0  # max distance (inches) from a cable end to a fan-out / rack

# Vectorworks symbol name -> ShowStack fan-out name
FANOUT_MAP = {
    "NL4 Y": "NL4 Y",
    "NL8 Y": "NL8 Y",
    "DoFill": "DOFill",
    "DoSub": "DOSub",
    "SUB Cable": "SUB Cable",
}

# Connectors an extension is expected to use
EXTENSION_CONNECTORS = ("SpeakerTwist4", "SpeakerTwist8")

# A symbol counts as an amp rack if its name contains any of these (case-insensitive)
RACK_KEYWORDS = ["RAK"]

report = []
fanouts = []   # (showstack_name, (x,y,z), symbol_name)
racks = []     # (destination, (x,y,z), symbol_name)
cables = []    # handles

def to_ft(val):
    s = str(val).strip().replace("'", "").replace('"', "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def xyz(p):
    """Flatten whatever Vectorworks returns into (x, y, z)."""
    flat = []
    def walk(v):
        if isinstance(v, (tuple, list)):
            for i in v:
                walk(i)
        else:
            try:
                flat.append(float(v))
            except (TypeError, ValueError):
                pass
    walk(p)
    while len(flat) < 3:
        flat.append(0.0)
    return (flat[0], flat[1], flat[2])


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def rec(h, record, field):
    try:
        v = vs.GetRField(h, record, field)
        return v if v else ""
    except Exception:
        return ""


def collect_symbols(h):
    name = vs.GetSymName(h)
    loc = xyz(vs.GetSymLoc3D(h))
    if name in FANOUT_MAP:
        fanouts.append((FANOUT_MAP[name], loc, name))
    elif any(k in name.upper() for k in RACK_KEYWORDS):
        dest = (rec(h, "EntEquipUniversal", "Unit Number")
                or rec(h, "EntEquipUniversal", "Location")
                or rec(h, "EntEquipUniversal", "Short Name")
                or name)
        racks.append((dest, loc, name))


def collect_cables(h):
    cables.append(h)


def endpoints(h):
    """Return (start, end, debug) in world coords. Assumes no 3D rotation on the cable."""
    origin = xyz(vs.GetSymLoc3D(h))
    dbg = []
    pts = []
    try:
        path = vs.GetCustomObjectPath(h)
        ptype = vs.GetTypeN(path)
        n = vs.GetVertNum(path)
        dbg.append("path type %s, %s vertices" % (ptype, n))
        raw = []
        if ptype == 111:  # NURBS curve: use its control points (first/last = ends)
            # NURBS calls take a piece index; try 0-based, then 1-based
            pieces = 0
            try:
                pieces = int(vs.NurbsNumPieces(path))
            except Exception as e:
                dbg.append("NurbsNumPieces err: %s" % e)
            if pieces < 1:
                # Fallback: probe piece indexes until NurbsGetNumPts fails or returns 0
                for k in range(0, 500):
                    try:
                        if int(vs.NurbsGetNumPts(path, k)) < 1:
                            break
                        pieces = k + 1
                    except Exception:
                        break
                dbg.append("pieces by probing")
            if pieces < 1:
                pieces = 1
            dbg.append("nurbs pieces %s" % pieces)
            for base in (0, 1):
                try:
                    first_piece = base
                    last_piece = base + pieces - 1
                    n_last = int(vs.NurbsGetNumPts(path, last_piece))
                    p_first = xyz(vs.NurbsGetPt3D(path, first_piece, base))
                    p_last = xyz(vs.NurbsGetPt3D(path, last_piece, base + n_last - 1))
                    raw = [p_first, p_last]
                    dbg.append("nurbs index base %d ok, last piece pts %d" % (base, n_last))
                    break
                except Exception as e:
                    dbg.append("nurbs base %d err: %s" % (base, e))
        else:
            for i in range(n):
                try:
                    if ptype == 25:  # 3D polygon
                        raw.append(xyz(vs.GetPolyPt3D(path, i)))
                    else:            # 2D polyline/polygon
                        raw.append(xyz(vs.GetPolylineVertex(path, i + 1)))
                except Exception as e:
                    dbg.append("vertex %d err: %s" % (i, e))
        if raw:
            dbg.append("raw first %s last %s" % (tuple(round(c, 1) for c in raw[0]),
                                                  tuple(round(c, 1) for c in raw[-1])))
            # Path points may be local (start near 0,0,0) or already world (start near origin)
            if dist(raw[0], origin) < 1.0:
                pts = raw
                dbg.append("path coords look WORLD")
            else:
                pts = [(origin[0] + p[0], origin[1] + p[1], origin[2] + p[2]) for p in raw]
                dbg.append("path coords look LOCAL")
    except Exception as e:
        dbg.append("path err: %s" % e)
    try:
        m = vs.GetEntityMatrix(h)
        dbg.append("matrix %s" % (m,))
    except Exception:
        pass
    if not pts:
        pts = [origin]
    return pts[0], pts[-1], dbg


def nearest(items, point):
    best, bd = None, None
    for it in items:
        d = dist(it[1], point)
        if bd is None or d < bd:
            best, bd = it, d
    return best, bd


vs.ForEachObject(collect_symbols, "(T=SYMBOL)")
vs.ForEachObject(collect_cables, "(R IN ['CableObject'])")

# ---- pass 1: measure every cable ----
info = []
for h in cables:
    start, end, dbg = endpoints(h)
    length = to_ft(rec(h, "CableObject", "Length"))
    spare = to_ft(rec(h, "CableObject", "Spare"))
    swag = to_ft(rec(h, "CableObject", "Swag"))
    c = {
        "h": h,
        "run_id": rec(h, "CableObject", "CableRun_ID"),
        "conn": rec(h, "CableObject", "StartConector"),
        "length": length,
        "total": round(length + spare + swag, 1),
        "ends": (start, end),
        "dbg": dbg,
        "kind": "unmatched",
        "rack": None, "rack_d": None,
        "fan_idx": None, "fan_d": None,
        "parent": None,
        "warn": [],
    }
    # rack at either end?
    for ei, pt in enumerate(c["ends"]):
        r, d = nearest(racks, pt)
        if r is not None and d <= TOL and (c["rack_d"] is None or d < c["rack_d"]):
            c["rack"], c["rack_d"], c["rack_end"] = r, d, ei
    info.append(c)


def nearest_fan_idx(pt):
    best, bd = None, None
    for i, f in enumerate(fanouts):
        d = dist(f[1], pt)
        if bd is None or d < bd:
            best, bd = i, d
    return best, bd


# ---- pass 2: main runs (rack at one end, fan-out at the other) ----
for c in info:
    if c["rack"] is None:
        continue
    c["kind"] = "main"
    far = c["ends"][1 - c["rack_end"]]
    i, d = nearest_fan_idx(far)
    if i is not None and d <= TOL:
        c["fan_idx"], c["fan_d"] = i, d
    if not c["run_id"]:
        c["warn"].append("no Cable Run ID (label) - fill it in")

# fan-out instance -> main run
fan_owner = {}
for c in info:
    if c["kind"] == "main" and c["fan_idx"] is not None:
        if c["fan_idx"] in fan_owner:
            c["warn"].append("two main runs end at the same fan-out")
        fan_owner[c["fan_idx"]] = c

# ---- pass 3: extensions (no rack, one end at a fan-out that a main run feeds) ----
for c in info:
    if c["kind"] == "main":
        continue
    best = None
    for pt in c["ends"]:
        i, d = nearest_fan_idx(pt)
        if i is not None and d <= TOL and (best is None or d < best[1]):
            best = (i, d)
    if best is None:
        c["warn"].append("not at a rack or fan-out - fill Destination by hand or move its end")
        continue
    c["fan_idx"], c["fan_d"] = best
    parent = fan_owner.get(best[0])
    if parent is None:
        c["warn"].append("starts at a fan-out but no main run ends there")
        continue
    c["kind"] = "extension"
    c["parent"] = parent
    if c["conn"] not in EXTENSION_CONNECTORS:
        c["warn"].append("extension connector is %s - expected NL4/NL8 (wrong style?)" % c["conn"])

# ---- report + write ----
report.append("DRY RUN" if DRY_RUN else "WRITE MODE")
report.append("Fan-outs: %d   Racks: %d   Cables: %d" % (len(fanouts), len(racks), len(cables)))
for f in fanouts:
    report.append("  fan-out %-10s at %s" % (f[0], tuple(round(v, 1) for v in f[1])))
for r in racks:
    report.append("  rack    %-14s at %s  (%s)" % (r[0], tuple(round(v, 1) for v in r[1]), r[2]))
report.append("")

for c in info:
    h = c["h"]
    fan_name = fanouts[c["fan_idx"]][0] if c["fan_idx"] is not None else ""
    label = c["run_id"] or "<no label>"
    report.append("[%s] '%s'  %s  length %.1f ft  total %.1f ft"
                  % (c["kind"].upper(), label, c["conn"], c["length"], c["total"]))
    s, e = c["ends"]
    report.append("   start %s  end %s" % (tuple(round(v, 1) for v in s), tuple(round(v, 1) for v in e)))
    if c["kind"] == "main":
        report.append("   rack: %s @ %.1f   fan-out: %s" % (
            c["rack"][0], c["rack_d"],
            ("%s @ %.1f" % (fan_name, c["fan_d"])) if fan_name else "none"))
    elif c["kind"] == "extension":
        report.append("   extension of '%s' at %s @ %.1f" % (c["parent"]["run_id"] or "<no label>", fan_name, c["fan_d"]))
    for w in c["warn"]:
        report.append("   WARNING: %s" % w)
    for d in c["dbg"]:
        report.append("   debug: %s" % d)

    if not DRY_RUN:
        if c["kind"] == "main":
            if fan_name:
                vs.SetRField(h, "CableObject", "UserField_1", fan_name)
            vs.SetRField(h, "CableObject", "UserField_2", c["rack"][0])
        elif c["kind"] == "extension" and c["parent"]["run_id"]:
            vs.SetRField(h, "CableObject", "Loom_ID", c["parent"]["run_id"])
        vs.SetRField(h, "CableObject", "UserField_3", str(c["total"]))
        vs.ResetObject(h)

path = os.path.expanduser("~/Desktop/showstack_link_report.txt")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(report))
n_main = sum(1 for c in info if c["kind"] == "main")
n_ext = sum(1 for c in info if c["kind"] == "extension")
n_warn = sum(1 for c in info if c["warn"])
vs.AlrtDialog("ShowStack linker: %d main runs, %d extensions, %d with warnings. Report on Desktop."
              % (n_main, n_ext, n_warn))
