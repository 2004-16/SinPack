"""Testes do gerador de dieline (pytest)."""
import re
import xml.etree.ElementTree as ET

import pytest

import dieline as D

SVG_NS = "{http://www.w3.org/2000/svg}"
SIZES = [(116, 30, 20), (80, 40, 15), (200, 90, 40), (60, 25, 12)]


def spec(C, L, A, **kw):
    return D.Spec(comprimento=C, largura=L, altura=A, **kw)


@pytest.mark.parametrize("C,L,A", SIZES)
def test_svg_valido(C, L, A):
    """O SVG gerado deve ser XML bem-formado."""
    svg = D.render_svg(spec(C, L, A))
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"


@pytest.mark.parametrize("C,L,A", SIZES)
def test_escala_mm(C, L, A):
    """width/height em mm e viewBox 1:1 (1 unidade = 1 mm)."""
    svg = D.render_svg(spec(C, L, A))
    root = ET.fromstring(svg)
    w = root.get("width")
    h = root.get("height")
    assert w.endswith("mm") and h.endswith("mm")
    vb = [float(x) for x in root.get("viewBox").split()]
    w_mm = float(w[:-2])
    h_mm = float(h[:-2])
    # viewBox precisa casar com as dimensões em mm (escala 1:1)
    assert abs(vb[2] - w_mm) < 1e-3
    assert abs(vb[3] - h_mm) < 1e-3
    # a tela precisa comportar o comprimento C
    assert w_mm > C


@pytest.mark.parametrize("C,L,A", SIZES)
def test_tamanho_blank_coerente(C, L, A):
    """Altura do blank ~ 2L + 2A + cola + margens (estrutura de 4 painéis)."""
    lo = D.build_layout(spec(C, L, A))
    s = lo.spec
    esperado = 2 * L + 2 * A + s.aba_cola
    medido = lo.ySb - lo.y_top + s.aba_cola
    assert abs(medido - esperado) < 1e-6


@pytest.mark.parametrize("C,L,A", SIZES)
def test_tuck_menor_que_profundidade(C, L, A):
    """A profundidade do tuck nunca pode exceder a profundidade da caixa (A)."""
    s = spec(C, L, A).resolved()
    assert s.prof_tuck <= A + 1e-9


@pytest.mark.parametrize("C,L,A", SIZES)
def test_dust_flaps_nao_colidem(C, L, A):
    """Duas dust flaps opostas dobram sobre a abertura L sem colidir (soma < L)."""
    s = spec(C, L, A).resolved()
    assert 2 * s.prof_dust < L + 1e-9


@pytest.mark.parametrize("C,L,A", SIZES)
def test_camadas_corte_e_vinco(C, L, A):
    """Devem existir camadas/grupos separados de corte e de vinco."""
    svg = D.render_svg(spec(C, L, A))
    assert 'id="corte"' in svg
    assert 'id="vinco"' in svg
    # cores distintas para faca e vinco
    assert D.STYLE["cut"]["stroke"] in svg
    assert D.STYLE["crease"]["stroke"] in svg


@pytest.mark.parametrize("C,L,A", SIZES)
def test_export_limpo_sem_cotas(C, L, A):
    """Export limpo não deve conter cotas nem construção."""
    svg = D.render_svg(spec(C, L, A, cotas=True), clean=True)
    assert 'id="cotas"' not in svg
    assert 'id="construcao"' not in svg
    # mas mantém faca e vinco
    assert 'id="corte"' in svg
    assert 'id="vinco"' in svg


@pytest.mark.parametrize("C,L,A", SIZES)
def test_contorno_fechado(C, L, A):
    """O contorno de corte principal é um caminho fechado (termina em Z)."""
    g = D.build_geometry(spec(C, L, A))
    assert g.outline.strip().endswith("Z")
    assert g.outline.startswith("M")


@pytest.mark.parametrize("C,L,A", SIZES)
def test_travas_presentes(C, L, A):
    """Com travas ligadas, existem fendas (slits) para receber os degraus."""
    g = D.build_geometry(spec(C, L, A, travas=True))
    # 2 slits por ponta x 2 pontas = 4
    assert len(g.cuts) >= 4


def test_toggle_travas_off():
    """Desligar travas remove as fendas de tongue."""
    g_on = D.build_geometry(spec(116, 30, 20, travas=True, slit_lock=False))
    g_off = D.build_geometry(spec(116, 30, 20, travas=False, slit_lock=False))
    assert len(g_on.cuts) > len(g_off.cuts)


def test_vinco_cola_vermelho():
    """A dobra da aba de cola usa o vinco vermelho."""
    svg = D.render_svg(spec(116, 30, 20))
    assert "vinco-cola" in svg
    assert D.STYLE["crease_red"]["stroke"] in svg


@pytest.mark.parametrize("C,L,A", SIZES)
def test_cli(tmp_path, C, L, A):
    """A CLI grava um arquivo SVG válido em UTF-8."""
    out = tmp_path / "t.svg"
    rc = D.main(["-C", str(C), "-L", str(L), "-A", str(A), "-o", str(out)])
    assert rc == 0
    data = out.read_text(encoding="utf-8")
    assert data.startswith("<?xml")
    ET.fromstring(data)


def test_rounded_path_quadrado():
    """rounded_path de um quadrado com raio 0 produz 4 cantos e fecha."""
    verts = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
    d = D.rounded_path(verts, closed=True)
    assert d.endswith("Z")
    assert d.count("L") == 4
