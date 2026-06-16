#!/usr/bin/env python3
"""
SinPack — Gerador paramétrico de dieline (blank) para cartuchos tuck-end.

Estilo de aba: lingueta de travamento de cantos arredondados com dois degraus
(tongue-and-slit lock) + abas de retenção (dust flaps) + slit-lock com recorte
de dedo, no painel adjacente.

Saída: SVG em escala 1:1 (1 unidade = 1 mm), camadas separadas de corte e vinco.

Uso (CLI):
    python dieline.py --comprimento 116 --largura 30 --altura 20 -o saida.svg

As funções de geometria são puras e testáveis (ver test_dieline.py).
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field, replace
from typing import List, Tuple

Point = Tuple[float, float]

# ---------------------------------------------------------------------------
# Convenções de linha (cores / tracejados) — pedido do die house.
# ---------------------------------------------------------------------------
STYLE = {
    # corte (faca): linha sólida. Cor estilo "CutContour" (spot magenta comum).
    "cut": {"stroke": "#E5007E", "stroke-width": 0.25, "dash": None},
    # vinco principal: tracejado cinza.
    "crease": {"stroke": "#96989A", "stroke-width": 0.25, "dash": "2,1.2"},
    # vinco/cola: tracejado vermelho.
    "crease_red": {"stroke": "#ED3237", "stroke-width": 0.25, "dash": "2,1.2"},
    # linha de construção: pontilhada fina.
    "construct": {"stroke": "#9aa0a6", "stroke-width": 0.15, "dash": "0.4,1.0"},
    # cotas / rótulos.
    "dim": {"stroke": "#3a7bd5", "stroke-width": 0.2, "dash": None},
}


# ---------------------------------------------------------------------------
# Especificação paramétrica
# ---------------------------------------------------------------------------
@dataclass
class Spec:
    # Medidas principais (mm)
    comprimento: float          # C — dimensão longa (horizontal no blank)
    largura: float              # L — largura da seção (paineis frente/verso)
    altura: float               # A — altura/profundidade (paineis laterais)

    # Avançados (defaults derivados quando None)
    espessura: float = 0.4      # espessura do material (mm) -> folgas
    aba_cola: float | None = None     # largura da aba de cola (seam)
    prof_tuck: float | None = None    # profundidade da lingueta de trava
    prof_dust: float | None = None    # profundidade das abas de retenção
    raio: float | None = None         # raio dos cantos arredondados
    tongue_len: float | None = None   # protrusão dos degraus de trava
    tongue_w: float | None = None     # largura (na vertical) de cada degrau
    slit_w: float | None = None       # largura do slit-lock
    slit_h: float | None = None       # altura do slit-lock

    # Toggles
    travas: bool = True         # ligar tongue-and-slit lock
    slit_lock: bool = True      # desenhar slit-lock + recorte de dedo
    cotas: bool = True          # desenhar cotas / rótulos
    bleed: float = 0.0          # sangria (mm); 0 = sem
    registro: bool = False      # marcas de registro
    margem: float = 8.0         # margem ao redor do blank (mm)

    def resolved(self) -> "Spec":
        """Devolve uma cópia com todos os defaults derivados preenchidos."""
        C, L, A, t = self.comprimento, self.largura, self.altura, self.espessura
        d = dict(
            aba_cola=self.aba_cola if self.aba_cola is not None else _clamp(min(L, A) * 0.55, 6, 18),
            # tuck entra na caixa: profundidade <= altura A, com folga de material.
            prof_tuck=self.prof_tuck if self.prof_tuck is not None else max(A - 1.5 * t, 4.0),
            # dust flaps de painel lateral (altura A) dobram sobre a abertura L:
            # cada uma <= L/2 - folga para não colidirem.
            prof_dust=self.prof_dust if self.prof_dust is not None else _clamp(min(A * 0.85, L / 2 - 1.5 * t), 4.0, max(A, 6)),
            raio=self.raio if self.raio is not None else _clamp(min(L, A) * 0.18, 1.5, 6.0),
            tongue_len=self.tongue_len if self.tongue_len is not None else _clamp(min(L, A) * 0.06, 1.2, 3.5),
            tongue_w=self.tongue_w if self.tongue_w is not None else _clamp(L * 0.11, 3.0, 10.0),
            slit_w=self.slit_w if self.slit_w is not None else _clamp(A * 0.5, 4.0, 14.0),
            slit_h=self.slit_h if self.slit_h is not None else _clamp(L * 0.28, 6.0, 22.0),
        )
        return replace(self, **d)


def _clamp(v: float, lo: float, hi: float) -> float:
    if hi < lo:
        lo, hi = hi, lo
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Geometria — núcleo
# ---------------------------------------------------------------------------
@dataclass
class Layout:
    """Coordenadas-chave do blank, em mm (y cresce para baixo)."""
    spec: Spec
    x0: float          # esquerda do corpo (após abas esquerdas)
    xC: float          # direita do corpo
    y_top: float       # topo (borda livre da frente)
    yF: float          # base painel FRENTE
    ySt: float         # base painel LATERAL superior
    yB: float          # base painel VERSO
    ySb: float         # base painel LATERAL inferior
    yG: float          # base aba de cola
    width: float
    height: float


def build_layout(spec: Spec) -> Layout:
    s = spec.resolved()
    C, L, A = s.comprimento, s.largura, s.altura
    # excursão máxima de aba (para dimensionar a tela)
    fmax = max(s.prof_tuck + (s.tongue_len if s.travas else 0.0), s.prof_dust)
    M = s.margem + s.bleed
    x0 = M + fmax
    xC = x0 + C
    y_top = M
    yF = y_top + L
    ySt = yF + A
    yB = ySt + L
    ySb = yB + A
    yG = ySb + s.aba_cola
    width = xC + fmax + M
    height = yG + M
    return Layout(s, x0, xC, y_top, yF, ySt, yB, ySb, yG, width, height)


# --- polilinha com cantos arredondados -------------------------------------
def rounded_path(verts: List[Tuple[float, float, float]], closed: bool = True) -> str:
    """
    Converte uma lista de vértices (x, y, raio) em um path SVG com cantos
    arredondados via Béziers quadráticas. Funciona para cantos convexos e
    côncavos (raio aplicado conforme a geometria local).
    """
    n = len(verts)
    if n < 2:
        return ""
    pts = [(x, y) for (x, y, _r) in verts]
    rads = [r for (_x, _y, r) in verts]

    def sub(a: Point, b: Point) -> Point:
        return (a[0] - b[0], a[1] - b[1])

    def norm(a: Point) -> Point:
        d = math.hypot(a[0], a[1])
        return (0.0, 0.0) if d == 0 else (a[0] / d, a[1] / d)

    def dist(a: Point, b: Point) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    segs: List[str] = []
    first_after: Point | None = None

    for i in range(n):
        if not closed and (i == 0 or i == n - 1):
            # endpoints sem arredondamento
            continue

    # Construção genérica: para cada vértice calcula corte A (antes) e B (depois)
    A_list: List[Point] = []
    B_list: List[Point] = []
    for i in range(n):
        vp = pts[(i - 1) % n]
        vi = pts[i]
        vn = pts[(i + 1) % n]
        r = rads[i]
        if r <= 0:
            A_list.append(vi)
            B_list.append(vi)
            continue
        din = norm(sub(vi, vp))
        dout = norm(sub(vn, vi))
        cut = min(r, 0.5 * dist(vp, vi), 0.5 * dist(vi, vn))
        A_list.append((vi[0] - din[0] * cut, vi[1] - din[1] * cut))
        B_list.append((vi[0] + dout[0] * cut, vi[1] + dout[1] * cut))

    if closed:
        d = [f"M {B_list[-1][0]:.4f} {B_list[-1][1]:.4f}"]
        for i in range(n):
            d.append(f"L {A_list[i][0]:.4f} {A_list[i][1]:.4f}")
            if rads[i] > 0:
                d.append(f"Q {pts[i][0]:.4f} {pts[i][1]:.4f} {B_list[i][0]:.4f} {B_list[i][1]:.4f}")
        d.append("Z")
        return " ".join(d)
    else:
        d = [f"M {pts[0][0]:.4f} {pts[0][1]:.4f}"]
        for i in range(1, n - 1):
            d.append(f"L {A_list[i][0]:.4f} {A_list[i][1]:.4f}")
            if rads[i] > 0:
                d.append(f"Q {pts[i][0]:.4f} {pts[i][1]:.4f} {B_list[i][0]:.4f} {B_list[i][1]:.4f}")
        d.append(f"L {pts[-1][0]:.4f} {pts[-1][1]:.4f}")
        return " ".join(d)


# --- perfis de aba ----------------------------------------------------------
def lock_flap(lo: Layout, y1: float, y2: float, sign: int) -> List[Tuple[float, float, float]]:
    """
    Lingueta de travamento (tuck-lock) de cantos arredondados com dois degraus
    e pescoços côncavos. `sign` = +1 (ponta direita) ou -1 (ponta esquerda).
    Vértices no sentido horário do contorno externo.
    """
    s = lo.spec
    xb = lo.xC if sign > 0 else lo.x0
    d = s.prof_tuck
    tl = s.tongue_len if s.travas else 0.0
    r = s.raio
    gap = s.espessura + 0.6                     # folga de canto (relevo)
    h = y2 - y1
    ya, yb = y1 + gap, y2 - gap
    thw = s.tongue_w / 2.0
    yt1 = y1 + h * 0.27
    yt2 = y1 + h * 0.73
    ox = lambda dd: xb + sign * dd              # deslocamento para fora
    rn = min(0.8, tl * 0.4) if tl > 0 else 0.0  # raio dos degraus/pescoços
    body = ox(d)
    tip = ox(d + tl)
    mid = ox(d + tl * 0.30)                     # leve convexidade central

    v: List[Tuple[float, float, float]] = []
    v.append((xb, ya, 0.0))                     # base topo
    v.append((body, ya, r))                     # canto externo superior
    if tl > 0:
        v.append((body, yt1 - thw, rn))         # pescoço (côncavo)
        v.append((tip, yt1 - thw, rn))          # degrau 1 — topo
        v.append((tip, yt1 + thw, rn))          # degrau 1 — base
        v.append((body, yt1 + thw, rn))         # volta ao corpo (côncavo)
        v.append((mid, (yt1 + yt2) / 2.0, r))   # convexidade central
        v.append((body, yt2 - thw, rn))
        v.append((tip, yt2 - thw, rn))
        v.append((tip, yt2 + thw, rn))
        v.append((body, yt2 + thw, rn))
    v.append((body, yb, r))                     # canto externo inferior
    v.append((xb, yb, 0.0))                     # base inferior
    return v


def dust_flap(lo: Layout, y1: float, y2: float, sign: int, depth: float) -> List[Tuple[float, float, float]]:
    """Aba de retenção / poeira: retângulo de cantos arredondados."""
    s = lo.spec
    xb = lo.xC if sign > 0 else lo.x0
    r = s.raio
    gap = s.espessura + 0.6
    ya, yb = y1 + gap, y2 - gap
    ox = xb + sign * depth
    return [
        (xb, ya, 0.0),
        (ox, ya, r),
        (ox, yb, r),
        (xb, yb, 0.0),
    ]


# --- contorno externo completo ---------------------------------------------
def outline_vertices(lo: Layout) -> List[Tuple[float, float, float]]:
    s = lo.spec
    x0, xC = lo.x0, lo.xC
    yt, yF, ySt, yB, ySb, yG = lo.y_top, lo.yF, lo.ySt, lo.yB, lo.ySb, lo.yG
    ch = s.raio  # chanfro nos cantos da borda livre superior
    dust = s.prof_dust

    v: List[Tuple[float, float, float]] = []

    # Borda superior (livre) da FRENTE, com cantos chanfrados arredondados.
    v.append((x0 + ch, yt, ch))
    v.append((xC - ch, yt, ch))

    # ----- Lado DIREITO, de cima para baixo -----
    v += lock_flap(lo, yt, yF, +1)          # FRENTE: lingueta de trava
    v += dust_flap(lo, yF, ySt, +1, dust)   # LATERAL sup: dust flap
    v += dust_flap(lo, ySt, yB, +1, dust)   # VERSO: dust flap (recebe trava)
    v += dust_flap(lo, yB, ySb, +1, dust)   # LATERAL inf: dust flap

    # Aba de cola (seam) na base — chanfrada nas pontas.
    gc = min(s.aba_cola, 6.0)
    v.append((xC, ySb, 0.0))
    v.append((xC - gc, yG, s.raio * 0.5))
    v.append((x0 + gc, yG, s.raio * 0.5))
    v.append((x0, ySb, 0.0))

    # ----- Lado ESQUERDO, de baixo para cima (espelho) -----
    v += list(reversed(dust_flap(lo, yB, ySb, -1, dust)))
    v += list(reversed(dust_flap(lo, ySt, yB, -1, dust)))
    v += list(reversed(dust_flap(lo, yF, ySt, -1, dust)))
    v += list(reversed(lock_flap(lo, yt, yF, -1)))

    return v


# --- linhas internas (vincos, construção, slits) ----------------------------
@dataclass
class Geometry:
    layout: Layout
    outline: str
    creases: List[Tuple[str, str]] = field(default_factory=list)   # (path, estilo)
    cuts: List[Tuple[str, str]] = field(default_factory=list)
    construct: List[Tuple[str, str]] = field(default_factory=list)


def line(x1, y1, x2, y2) -> str:
    return f"M {x1:.4f} {y1:.4f} L {x2:.4f} {y2:.4f}"


def slit_lock_paths(lo: Layout, sign: int) -> Tuple[List[str], List[str]]:
    """
    Slit-lock no painel VERSO, perto da ponta: fenda curva "(" + duas marcas
    perpendiculares (recorte de dedo) + retângulo tracejado (score).
    Retorna (cortes, vincos).
    """
    s = lo.spec
    xb = lo.xC if sign > 0 else lo.x0
    cy = (lo.ySt + lo.yB) / 2.0           # centro do painel VERSO
    inset = s.prof_dust * 0.45 + 3.0
    cx = xb - sign * inset
    w, hh = s.slit_w, s.slit_h
    cuts: List[str] = []
    creases: List[str] = []

    # Fenda curva "(" (concavidade apontando para fora)
    bow = sign * w * 0.5
    top = (cx - bow * 0.15, cy - hh / 2)
    bot = (cx - bow * 0.15, cy + hh / 2)
    ctrl = (cx + bow, cy)
    cuts.append(f"M {top[0]:.4f} {top[1]:.4f} Q {ctrl[0]:.4f} {ctrl[1]:.4f} {bot[0]:.4f} {bot[1]:.4f}")
    # marcas perpendiculares curtas nas pontas da fenda
    tick = sign * 2.2
    cuts.append(line(top[0], top[1], top[0] - tick, top[1]))
    cuts.append(line(bot[0], bot[1], bot[0] - tick, bot[1]))

    # retângulo tracejado (score / vinco) ao redor
    rx1, rx2 = cx - sign * (w * 0.55), cx + sign * (w * 0.95)
    ry1, ry2 = cy - hh * 0.62, cy + hh * 0.62
    rx1, rx2 = min(rx1, rx2), max(rx1, rx2)
    creases.append(
        f"M {rx1:.4f} {ry1:.4f} L {rx2:.4f} {ry1:.4f} L {rx2:.4f} {ry2:.4f} L {rx1:.4f} {ry2:.4f} Z"
    )
    return cuts, creases


def tongue_slits(lo: Layout, sign: int) -> List[str]:
    """Fendas (slits) no painel VERSO que recebem os degraus da lingueta."""
    s = lo.spec
    xb = lo.xC if sign > 0 else lo.x0
    y1, y2 = lo.ySt, lo.yB
    h = y2 - y1
    yt1 = y1 + h * 0.27
    yt2 = y1 + h * 0.73
    inset = 2.5 + s.espessura
    sx = xb - sign * inset
    sw = s.tongue_w + 2 * s.espessura      # folga de material
    out: List[str] = []
    for yc in (yt1, yt2):
        out.append(line(sx, yc - sw / 2, sx, yc + sw / 2))
    return out


def build_geometry(spec: Spec) -> Geometry:
    lo = build_layout(spec)
    s = lo.spec
    g = Geometry(layout=lo, outline=rounded_path(outline_vertices(lo), closed=True))

    # Vincos do corpo (horizontais) entre painéis.
    for y in (lo.yF, lo.ySt, lo.yB, lo.ySb):
        g.creases.append((line(lo.x0, y, lo.xC, y), "crease"))
    # Vinco da aba de cola em vermelho (já incluso acima como ySb -> sobrescreve)
    g.creases[-1] = (line(lo.x0, lo.ySb, lo.xC, lo.ySb), "crease_red")

    # Vincos verticais das abas (dobras das pontas).
    gap = s.espessura + 0.6
    spans = [(lo.y_top, lo.yF), (lo.yF, lo.ySt), (lo.ySt, lo.yB), (lo.yB, lo.ySb)]
    for (y1, y2) in spans:
        for x in (lo.x0, lo.xC):
            g.creases.append((line(x, y1 + gap, x, y2 - gap), "crease"))

    # Travas + slit-locks nas duas pontas.
    if s.travas:
        for sign in (+1, -1):
            for p in tongue_slits(lo, sign):
                g.cuts.append((p, "cut"))
    if s.slit_lock:
        for sign in (+1, -1):
            sc, cr = slit_lock_paths(lo, sign)
            for p in sc:
                g.cuts.append((p, "cut"))
            for p in cr:
                g.creases.append((p, "crease"))

    # Linhas de construção (auxiliares de dobra do tuck) — pontilhadas.
    g.construct.append((line(lo.x0, lo.ySt + (lo.yB - lo.ySt) * 0.18, lo.xC, lo.ySt + (lo.yB - lo.ySt) * 0.18), "construct"))

    return g


# ---------------------------------------------------------------------------
# Renderização SVG
# ---------------------------------------------------------------------------
def _style_attr(name: str) -> str:
    st = STYLE[name]
    dash = f';stroke-dasharray:{st["dash"]}' if st["dash"] else ""
    return f'fill:none;stroke:{st["stroke"]};stroke-width:{st["stroke-width"]}{dash}'


def render_svg(spec: Spec, clean: bool = False) -> str:
    g = build_geometry(spec)
    lo = g.layout
    s = lo.spec
    W, H = lo.width, lo.height

    out: List[str] = []
    out.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{W:.3f}mm" height="{H:.3f}mm" viewBox="0 0 {W:.3f} {H:.3f}">'
    )
    out.append(f'  <title>SinPack dieline {s.comprimento}x{s.largura}x{s.altura} mm</title>')
    out.append('  <style>')
    out.append(f'    .corte {{ {_style_attr("cut")} }}')
    out.append(f'    .vinco {{ {_style_attr("crease")} }}')
    out.append(f'    .vinco-cola {{ {_style_attr("crease_red")} }}')
    out.append(f'    .construcao {{ {_style_attr("construct")} }}')
    out.append(f'    .cota {{ {_style_attr("dim")} }}')
    out.append('    text { font-family: sans-serif; fill: #3a7bd5; }')
    out.append('  </style>')

    if s.bleed > 0:
        out.append(f'  <rect x="{s.bleed:.3f}" y="{s.bleed:.3f}" width="{W-2*s.bleed:.3f}" '
                   f'height="{H-2*s.bleed:.3f}" fill="none" stroke="#cccccc" stroke-width="0.1" stroke-dasharray="1,1"/>')

    # Camada VINCO
    out.append('  <g id="vinco" inkscape:groupmode="layer" inkscape:label="vinco">')
    for path, st in g.creases:
        cls = "vinco-cola" if st == "crease_red" else "vinco"
        out.append(f'    <path class="{cls}" d="{path}"/>')
    out.append('  </g>')

    # Camada CONSTRUÇÃO (omitida no modo limpo)
    if not clean:
        out.append('  <g id="construcao" inkscape:groupmode="layer" inkscape:label="construcao">')
        for path, st in g.construct:
            out.append(f'    <path class="construcao" d="{path}"/>')
        out.append('  </g>')

    # Camada CORTE (contorno + slits) — por cima
    out.append('  <g id="corte" inkscape:groupmode="layer" inkscape:label="corte">')
    out.append(f'    <path class="corte" d="{g.outline}"/>')
    for path, st in g.cuts:
        out.append(f'    <path class="corte" d="{path}"/>')
    out.append('  </g>')

    # Cotas / rótulos (omitidas no modo limpo)
    if s.cotas and not clean:
        out.append('  <g id="cotas" inkscape:groupmode="layer" inkscape:label="cotas">')
        fs = max(3.0, min(lo.width, lo.height) * 0.02)
        # C ao longo do topo
        out.append(_dim_h(lo.x0, lo.xC, lo.y_top - 4, f"C = {s.comprimento:g} mm", fs))
        # L e A na lateral esquerda
        out.append(_dim_v(lo.x0 - 4, lo.y_top, lo.yF, f"L={s.largura:g}", fs))
        out.append(_dim_v(lo.x0 - 4, lo.yF, lo.ySt, f"A={s.altura:g}", fs))
        out.append('  </g>')

    out.append('</svg>')
    # Atributos de namespace inkscape (para rótulos de camada)
    svg = "\n".join(out).replace(
        '<svg xmlns="http://www.w3.org/2000/svg"',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"',
    )
    return svg


def _dim_h(x1, x2, y, label, fs) -> str:
    return (f'    <path class="cota" d="M {x1:.2f} {y:.2f} L {x2:.2f} {y:.2f}"/>'
            f'<text x="{(x1+x2)/2:.2f}" y="{y-1:.2f}" font-size="{fs:.2f}" text-anchor="middle">{label}</text>')


def _dim_v(x, y1, y2, label, fs) -> str:
    return (f'    <path class="cota" d="M {x:.2f} {y1:.2f} L {x:.2f} {y2:.2f}"/>'
            f'<text x="{x-1:.2f}" y="{(y1+y2)/2:.2f}" font-size="{fs:.2f}" '
            f'text-anchor="middle" transform="rotate(-90 {x-1:.2f} {(y1+y2)/2:.2f})">{label}</text>')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gerador paramétrico de dieline tuck-end (SinPack).")
    p.add_argument("--comprimento", "-C", type=float, required=True, help="Comprimento C (mm)")
    p.add_argument("--largura", "-L", type=float, required=True, help="Largura L (mm)")
    p.add_argument("--altura", "-A", type=float, required=True, help="Altura A (mm)")
    p.add_argument("--espessura", type=float, default=0.4, help="Espessura do material (mm)")
    p.add_argument("--aba-cola", type=float, default=None, help="Largura da aba de cola (mm)")
    p.add_argument("--sem-travas", action="store_true", help="Desligar tongue-and-slit lock")
    p.add_argument("--sem-slit", action="store_true", help="Desligar slit-lock/recorte de dedo")
    p.add_argument("--bleed", type=float, default=0.0, help="Sangria (mm)")
    p.add_argument("--limpo", action="store_true", help="Export limpo: só faca + vinco")
    p.add_argument("-o", "--output", default="saida.svg", help="Arquivo SVG de saída")
    a = p.parse_args(argv)

    spec = Spec(
        comprimento=a.comprimento, largura=a.largura, altura=a.altura,
        espessura=a.espessura, aba_cola=a.aba_cola,
        travas=not a.sem_travas, slit_lock=not a.sem_slit,
        bleed=a.bleed, cotas=not a.limpo,
    )
    svg = render_svg(spec, clean=a.limpo)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(svg)
    lo = build_layout(spec)
    print(f"OK: {a.output}  ({lo.width:.1f} x {lo.height:.1f} mm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
