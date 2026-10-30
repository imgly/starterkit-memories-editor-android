"""Generates the two Memories style backdrops as looping Lottie animations.

Both are deliberately tiny. Measured on a Nothing Phone (2a), the cost of a
Lottie backdrop tracks how much geometry it draws per frame: a full-frame
gradient renders faster than the video it replaces (p90 26ms vs 31ms), ~40
stroked paths match it, and 120 does not (101ms). An earlier design with ~400
strokes, four blurs and three blend layers stalled the main thread for 450ms.

So: Hologram is one light and a ground, and Bubblegum is two gradients whose
bright band migrates -- no shape moves in it at all. Neither uses an effect or
a blend mode.

The composition rules come from ambient-backdrop research: the backdrop sits a
stop under the photos, carries exactly one hotspot placed behind the photo card,
has no luminance edge sharper than ~120px, and every motion period divides the
10s loop so it closes in velocity as well as position.

Note for anyone extending this: Lottie's radial highlight parameters (h/a) are
ignored by this Skottie build, so an off-centre specular has to come from
offsetting the gradient's start point. Animated gradient STOP positions do work,
and are the cheapest motion available -- that is what drives Bubblegum.
"""

import json, math, os, sys

FR, DUR = 30, 10.0
OP = int(FR * DUR)
W, H = 1080, 1920
NK = 24
BM_NORMAL, BM_MULTIPLY, BM_SCREEN = 0, 1, 2


# ── colour ───────────────────────────────────────────────────────────────
def hexc(s):
    s = s.lstrip('#')
    return [round(int(s[i : i + 2], 16) / 255, 3) for i in (0, 2, 4)]


def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _to_oklab(rgb):
    r, g, b = (_srgb_to_lin(v) for v in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    t = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * t,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * t,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * t,
    )


def _to_rgb(lab):
    L, A, B = lab
    l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
    m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
    t = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3
    return [
        round(_lin_to_srgb(v), 4)
        for v in (
            4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * t,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * t,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * t,
        )
    ]


def oklab_ramp(stops, n=13):
    """Perceptual resample; sRGB interpolation between saturated hues goes muddy."""
    pos = [p for p, _ in stops]
    labs = [_to_oklab(hexc(c)) for _, c in stops]
    out = []
    for i in range(n):
        u = i / (n - 1)
        k = max(0, min(len(pos) - 2, next((j for j in range(len(pos) - 1) if pos[j] <= u <= pos[j + 1]), len(pos) - 2)))
        span = pos[k + 1] - pos[k]
        t = 0.0 if span <= 0 else (u - pos[k]) / span
        out.append((round(u, 4), _to_rgb(tuple(labs[k][c] + (labs[k + 1][c] - labs[k][c]) * t for c in range(3)))))
    return out


def grad(stops, alphas=None):
    out = []
    for pos, c in oklab_ramp(stops):
        out += [round(pos, 3)] + c
    for pos, a in alphas or []:
        out += [round(pos, 3), round(a, 3)]
    return out


def gstops(stops):
    return len(oklab_ramp(stops))


# ── animation ────────────────────────────────────────────────────────────
def stat(v):
    return {"a": 0, "k": v}


def _kf(t, s):
    return {"t": round(t, 2), "s": s, "i": {"x": [1], "y": [1]}, "o": {"x": [0], "y": [0]}}


def _assert_periodic(fn, what):
    a, b = fn(0.0), fn(1.0)
    fa = [c for x in (a if isinstance(a, (list, tuple)) else [a]) for c in (x if isinstance(x, (list, tuple)) else [x])]
    fb = [c for x in (b if isinstance(b, (list, tuple)) else [b]) for c in (x if isinstance(x, (list, tuple)) else [x])]
    worst = max((abs(x - y) for x, y in zip(fa, fb)), default=0.0)
    if worst > 1e-6:
        raise AssertionError(f"{what} not periodic over the loop: f(0) vs f(1) differ by {worst:.3f}")


def anim(fn, n=NK):
    _assert_periodic(fn, "value")
    ks = []
    for i in range(n + 1):
        v = fn((i % n) / n)
        v = [round(x, 1) for x in v] if isinstance(v, (list, tuple)) else [round(v, 1)]
        ks.append(_kf(i * OP / n, v))
    return {"a": 1, "k": ks}


def anim_path(fn, n=NK, closed=False):
    _assert_periodic(fn, "path")
    ks = []
    for i in range(n + 1):
        pts = fn((i % n) / n)
        v = [[round(x, 1), round(y, 1)] for x, y in pts]
        it, ot = [], []
        for j in range(len(v)):
            p0 = v[j - 1] if (closed or j > 0) else v[0]
            p1 = v[(j + 1) % len(v)] if (closed or j < len(v) - 1) else v[-1]
            tx, ty = (p1[0] - p0[0]) / 3.0, (p1[1] - p0[1]) / 3.0
            it.append([round(-tx, 1), round(-ty, 1)])
            ot.append([round(tx, 1), round(ty, 1)])
        ks.append(_kf(i * OP / n, [{"i": it, "o": ot, "v": v, "c": closed}]))
    return {"a": 1, "k": ks}


# ── structure ────────────────────────────────────────────────────────────
def tr(p=None, a=None, s=None, r=None, o=None):
    return {
        "ty": "tr",
        "p": p or stat([0, 0]),
        "a": a or stat([0, 0]),
        "s": s or stat([100, 100]),
        "r": r or stat(0),
        "o": o or stat(100),
    }


def layer(shapes, name="L", blend=BM_NORMAL, blur=None, opacity=100, rot=0):
    l = {
        "ddd": 0,
        "ind": 0,
        "ty": 4,
        "nm": name,
        "sr": 1,
        "ks": {
            "o": opacity if isinstance(opacity, dict) else stat(opacity),
            "r": rot if isinstance(rot, dict) else stat(rot),
            "p": stat([W / 2, H / 2]),
            "a": stat([W / 2, H / 2]),
            "s": stat([100, 100]),
        },
        "ao": 0,
        "shapes": shapes,
        "ip": 0,
        "op": OP,
        "st": 0,
        "bm": blend,
    }
    if blur:
        l["ef"] = [
            {
                "ty": 5,
                "nm": "GB",
                "np": 3,
                "mn": "ADBE Gaussian Blur 2",
                "ix": 1,
                "ef": [
                    {"ty": 0, "nm": "Blurriness", "v": blur if isinstance(blur, dict) else stat(blur)},
                    {"ty": 7, "nm": "D", "v": stat(1)},
                    {"ty": 7, "nm": "R", "v": stat(1)},
                ],
            }
        ]
    return l


def comp(layers, name):
    for i, l in enumerate(layers):
        l["ind"] = i + 1
    return {
        "v": "5.7.4",
        "fr": FR,
        "ip": 0,
        "op": OP,
        "w": W,
        "h": H,
        "nm": name,
        "ddd": 0,
        "assets": [],
        "layers": layers,
    }


# ── shapes ───────────────────────────────────────────────────────────────
def gfill(stops, start, end, gtype=1, alphas=None, opacity=100):
    return {
        "ty": "gf",
        "o": stat(opacity),
        "r": 1,
        "t": gtype,
        "s": start if isinstance(start, dict) else stat(start),
        "e": end if isinstance(end, dict) else stat(end),
        "g": {"p": gstops(stops), "k": stat(grad(stops, alphas))},
        "nm": "g",
    }


def gfill_anim(stops_fn, start, end, gtype=1, alphas_fn=None, opacity=100, n=NK):
    """A fill whose gradient STOPS animate.

    Migrating a bright band along the ramp moves light across the frame without
    moving a single shape — the cheapest motion available, and the only one the
    old design never used. (The radial highlight params h/a are ignored by this
    Skottie build, so an off-centre specular has to come from the start point.)
    """
    _assert_periodic(lambda u: [p for p, _ in stops_fn(u)], "stop positions")
    ks = []
    for i in range(n + 1):
        u = (i % n) / n
        ks.append(_kf(i * OP / n, grad(stops_fn(u), alphas_fn(u) if alphas_fn else None)))
    return {
        "ty": "gf",
        "o": stat(opacity),
        "r": 1,
        "t": gtype,
        "s": start if isinstance(start, dict) else stat(start),
        "e": end if isinstance(end, dict) else stat(end),
        "g": {"p": gstops(stops_fn(0.0)), "k": {"a": 1, "k": ks}},
        "nm": "g",
    }


def sheen_ramp(base, band_colour, band_pos, band_w=0.13):
    """base = [(pos,hex)...] with the band spliced in, so the ramp keeps its ends."""
    lo, hi = max(0.0, band_pos - band_w), min(1.0, band_pos + band_w)
    out = [(p, c) for p, c in base if p < lo - 0.02]
    out += [(lo, _nearest(base, lo)), (band_pos, band_colour), (hi, _nearest(base, hi))]
    out += [(p, c) for p, c in base if p > hi + 0.02]
    out = sorted({round(p, 4): c for p, c in out}.items())
    if out[0][0] > 0:
        out = [(0.0, base[0][1])] + out
    if out[-1][0] < 1:
        out = out + [(1.0, base[-1][1])]
    return out


def _nearest(base, pos):
    return min(base, key=lambda pc: abs(pc[0] - pos))[1]


def bg(stops, start=None, end=None, gtype=1):
    return layer(
        [
            {
                "ty": "gr",
                "nm": "bg",
                "it": [
                    {"ty": "rc", "p": stat([0, 0]), "s": stat([W * 1.7, H * 1.7]), "r": stat(0), "nm": "r"},
                    gfill(stops, start or [0, -H * 0.55], end or [0, H * 0.7], gtype),
                    tr(p=stat([W / 2, H / 2])),
                ],
            }
        ],
        "bg",
    )


C_FLOOR, C_DEEP, C_BODY, C_SHEEN, C_PEAK = "#0B1020", "#16233D", "#3A7FBF", "#7FB6DC", "#DCEEF9"
W_FLOOR, W_DEEP, W_BODY, W_WARM, W_PEAK = "#2A0E12", "#4E1A1B", "#E0533F", "#F58B5E", "#FFD9B0"

COOL_BG = [(0, C_DEEP), (0.45, "#101B31"), (1, C_FLOOR)]
WARM_BG = [(0, W_DEEP), (0.45, "#3A1216"), (1, W_FLOOR)]
COOL_RAMP = [(0, C_FLOOR), (0.30, C_DEEP), (0.62, C_BODY), (0.84, C_SHEEN), (1, C_PEAK)]
WARM_RAMP = [(0, W_FLOOR), (0.30, W_DEEP), (0.62, W_BODY), (0.84, W_WARM), (1, W_PEAK)]

# The one hotspot goes behind the photo card, upper-left of centre.
FX, FY = 0.38, 0.42


def sine(u, period=1, phase=0.0):
    return math.sin(2 * math.pi * (u / period + phase))


def core(colour, mid, floor, cx=FX, cy=FY, r=1500, peak=0.95, drift=0, phase=0.0, rate=1, sq=1.0, rot=0):
    """The single light. Alpha is gamma-bunched so it reads as a source, not a disc."""
    stops = [(0.0, colour), (0.22, mid), (0.55, floor), (1.0, floor)]
    alphas = [(0.0, peak), (0.10, peak * 0.74), (0.26, peak * 0.42), (0.55, peak * 0.14), (1.0, 0.0)]
    g = gfill(stops, [0, 0], [0, r], gtype=2, alphas=alphas)

    def pos(u):
        a = 2 * math.pi * (u / rate + phase)
        return [W * cx + drift * math.cos(a), H * cy + drift * 0.55 * math.sin(2 * a)]

    return {
        "ty": "gr",
        "nm": "core",
        "it": [
            {"ty": "el", "p": stat([0, 0]), "s": stat([r * 2, r * 2]), "nm": "e"},
            g,
            tr(p=anim(pos) if drift else stat([W * cx, H * cy]), s=stat([100, round(100 * sq, 2)]), r=stat(rot)),
        ],
    }


def sheen_layer(base, band, lo, hi, angle_deg, period=1, name="sheen", opacity=100, alpha_peak=1.0):
    """Full-frame rect whose bright band migrates. No transform, no movement."""
    th = math.radians(angle_deg)
    d = 1500
    s0 = [W / 2 - d * math.cos(th), H / 2 - d * math.sin(th)]
    e0 = [W / 2 + d * math.cos(th), H / 2 + d * math.sin(th)]

    def stops_fn(u):
        p = lo + (hi - lo) * (0.5 + 0.5 * sine(u, period))
        return sheen_ramp(base, band, p)

    def alphas_fn(u):
        return [(0.0, 0.0), (0.12, alpha_peak), (0.88, alpha_peak), (1.0, 0.0)] if alpha_peak < 1.0 else None

    fill = gfill_anim(stops_fn, s0, e0, 1, alphas_fn if alpha_peak < 1.0 else None)
    return layer(
        [
            {
                "ty": "gr",
                "nm": "s",
                "it": [
                    {"ty": "rc", "p": stat([0, 0]), "s": stat([W * 1.8, H * 1.8]), "r": stat(0), "nm": "r"},
                    fill,
                    tr(p=stat([W / 2, H / 2])),
                ],
            }
        ],
        name,
        opacity=opacity,
    )


# ── Hologram: one light whose centre sits above the frame ────────────────
# The brightest pixel is never on screen, so there is nothing to fixate on --
# only the skirt of the glow reaches the frame.
def build_hologram():
    k = core(C_PEAK, C_SHEEN, C_FLOOR, cx=0.30, cy=-0.16, r=1700, peak=0.9, drift=75)
    return comp([layer([k], "sun"), bg(COOL_BG)], "hologram")


# ── Bubblegum: two gradients, one migrating band ─────────────────────────
# Nothing here moves. The bright band travels along the ramp instead, which is
# motion at zero geometry cost.
def build_bubblegum():
    return comp(
        [
            sheen_layer(WARM_RAMP, W_PEAK, 0.40, 0.70, 100, 1, "s1"),
            sheen_layer(WARM_RAMP, W_WARM, 0.70, 0.30, 92, 0.5, "s2", opacity=45),
            bg(WARM_BG),
        ],
        "bubblegum",
    )


def write(c, path):
    json.dump(c, open(path, "w"), separators=(",", ":"))
    return sum(len(l.get("shapes", [])) for l in c["layers"]), os.path.getsize(path)


if __name__ == "__main__":
    out = sys.argv[1]
    for name, fn in (("bubblegum", build_bubblegum), ("hologram", build_hologram)):
        shapes, size = write(fn(), f"{out}/{name}.json")
        print(f"{name}.json  {shapes} shapes  {size / 1024:.1f} KB")
