# SinPack — Gerador paramétrico de dieline (cartucho tuck-end)

Automatic Package Creator for Medical Devices.

Gera o **blank (faca/vinco) em SVG** de cartuchos de papel‑cartão tipo *tuck‑end*
com **lingueta de travamento arredondada (tongue‑and‑slit lock)**, abas de
retenção (dust flaps) e *slit‑lock* com recorte de dedo — a partir de **3 medidas**:
Comprimento (C), Largura (L) e Altura (A), em mm.

A saída sai em **escala 1:1 em mm** (1 unidade SVG = 1 mm), então abre no
CorelDRAW/Illustrator já no tamanho certo, com **camadas separadas de corte e
vinco**.

> Estrutura: tubo tuck‑end com a dimensão longa na horizontal — 4 paredes
> empilhadas (Frente `L` · Lateral `A` · Verso `L` · Lateral `A`) + aba de cola.
> As tampas ficam nas pontas: a Frente vira **lingueta de trava** (2 degraus +
> pescoços côncavos), as Laterais viram **dust flaps**, e o Verso recebe o
> **slit‑lock** que encaixa os degraus.

## Uso rápido (sem programar)

Abra **`index.html`** no navegador. Digite C, L e A, ajuste o que quiser nas
opções avançadas e clique em **Baixar SVG** (ou **SVG limpo**, só faca+vinco).
Funciona offline; a prévia atualiza em tempo real.

## Uso por linha de comando (Python)

Requer Python 3.9+. Não há dependências para gerar o SVG.

```bash
python dieline.py --comprimento 116 --largura 30 --altura 20 -o saida.svg
```

Opções:

| Flag | Descrição | Default |
|------|-----------|---------|
| `-C, --comprimento` | Comprimento C (mm) | — (obrigatório) |
| `-L, --largura` | Largura L (mm) | — (obrigatório) |
| `-A, --altura` | Altura A (mm) | — (obrigatório) |
| `--espessura` | Espessura do material (mm) → folgas de encaixe | 0.4 |
| `--aba-cola` | Largura da aba de cola (mm) | auto |
| `--sem-travas` | Desliga o tongue‑and‑slit lock | ligado |
| `--sem-slit` | Desliga o slit‑lock / recorte de dedo | ligado |
| `--bleed` | Sangria (mm) | 0 |
| `--limpo` | Export limpo: só faca + vinco (sem cotas) | — |
| `-o, --output` | Arquivo SVG de saída | `saida.svg` |

### Como biblioteca

```python
import dieline as D
spec = D.Spec(comprimento=116, largura=30, altura=20)
svg  = D.render_svg(spec)             # versão completa com cotas
svg2 = D.render_svg(spec, clean=True) # só faca+vinco
```

## Convenções de linha (camadas)

| Camada | Significado | Estilo |
|--------|-------------|--------|
| `corte` | faca (corte) | sólida, magenta `#E5007E` (estilo CutContour) |
| `vinco` | vincos/dobras | tracejado cinza `#96989A` |
| `vinco-cola` | dobra da aba de cola | tracejado vermelho `#ED3237` |
| `construcao` | auxiliares | pontilhado (omitido no export limpo) |
| `cotas` | medidas/rótulos | azul (omitido no export limpo) |

As cores e tracejados ficam centralizados no dicionário `STYLE` em `dieline.py`,
fáceis de trocar para o padrão do seu *die house* (spot/overprint).

## Garantias de fabricação

- Profundidade do tuck **≤ profundidade da caixa** (A).
- Dust flaps opostas **não colidem** ao dobrar (soma < L).
- Folga de material (espessura) aplicada nas fendas de encaixe.
- Aba de cola com dobra própria (vinco vermelho) e cantos chanfrados.

## Testes

```bash
pip install pytest
python -m pytest -q
```

Cobrem: SVG válido, escala mm 1:1, estrutura de 4 painéis, tuck ≤ profundidade,
dust flaps sem colisão, presença das camadas corte/vinco, export limpo, contorno
fechado e a CLI.

## Validação visual

Para conferir o desenho, renderize para PNG:

```bash
pip install cairosvg
python -c "import cairosvg; cairosvg.svg2png(url='saida.svg', write_to='saida.png', output_width=1400)"
```

## Arquivos

- `dieline.py` — núcleo de geometria + CLI (funções puras, testáveis).
- `index.html` — prévia/standalone com os 3 inputs e botão de download.
- `test_dieline.py` — suíte pytest.
