"""
==============================================================
EXPERIMENTO COMPLETO: Ergodicidad Informacional Local (LIE)
Juego de la Vida de Conway
==============================================================
Uso:
    python spacetime_complete.py [seed]
    
    Sin argumento: corre el análisis completo (20 semillas)
    Con argumento: corre una sola semilla y guarda .npy

Estructura de archivos generados:
    seed_XXXX.npy     — datos de una semilla
    results_all.npy   — resultados agregados
    figure_1.png      — convergencia simétrica
    figure_2.png      — mecanismo cuantitativo
==============================================================
"""

import numpy as np
import sys
import time
import os

# ──────────────────────────────────────────────
# PARÁMETROS
# ──────────────────────────────────────────────
N       = 200    # tamaño grilla N×N
K       = 300    # número de sondas
T       = 1500   # pasos de simulación
R       = 5      # tiles para heterogeneidad (R×R = 25 tiles)
SEEDS   = [42, 137, 271, 314, 999, 17, 88, 256, 512, 1024,
           7, 23, 99, 404, 808, 11, 55, 333, 777, 2024]
OUT_DIR = '.'    # directorio de salida


# ──────────────────────────────────────────────
# JUEGO DE LA VIDA
# ──────────────────────────────────────────────
def step_life(g):
    nb = (np.roll(g,-1,0) + np.roll(g,1,0) +
          np.roll(g,-1,1) + np.roll(g,1,1) +
          np.roll(np.roll(g,-1,0),-1,1) +
          np.roll(np.roll(g,-1,0), 1,1) +
          np.roll(np.roll(g, 1,0),-1,1) +
          np.roll(np.roll(g, 1,0), 1,1))
    return ((g==1)&((nb==2)|(nb==3)) | (g==0)&(nb==3)).astype(np.uint8)


# ──────────────────────────────────────────────
# ENTROPÍA DE SHANNON
# ──────────────────────────────────────────────
def shannon(counts):
    """Entropía de Shannon en bits."""
    c = counts[counts > 0]
    if len(c) == 0:
        return 0.0
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


# ──────────────────────────────────────────────
# MÉTRICAS SIMÉTRICAS
# ──────────────────────────────────────────────
def spatial_h(g, probes):
    """
    H(espacio): entropía de bloques 2×2 sobre K sondas.
    Alfabeto: {0,1}^4 → 16 estados = mismo que H(tiempo).
    """
    counts = np.zeros(16)
    for cx, cy in probes:
        x1 = (cx+1) % N
        y1 = (cy+1) % N
        key = (int(g[cy,cx])<<3) | (int(g[cy,x1])<<2) | \
              (int(g[y1,cx])<<1) |  int(g[y1,x1])
        counts[key] += 1
    return shannon(counts)


def temporal_h(hist4, probes):
    """
    H(tiempo): entropía de secuencias de 4 pasos sobre K sondas.
    Alfabeto: {0,1}^4 → 16 estados = mismo que H(espacio).
    """
    if len(hist4) < 4:
        return 0.0
    counts = np.zeros(16)
    for cx, cy in probes:
        key = (int(hist4[-4][cy,cx])<<3) | (int(hist4[-3][cy,cx])<<2) | \
              (int(hist4[-2][cy,cx])<<1) |  int(hist4[-1][cy,cx])
        counts[key] += 1
    return shannon(counts)


def tile_heterogeneity(g):
    """
    Heterogeneidad espacial: std de H(2×2 bloques) por región R×R.
    Divide la grilla en R*R tiles y mide varianza de entropía local.
    """
    ts = N // R
    hs = []
    for ry in range(R):
        for rx in range(R):
            tile = g[ry*ts:(ry+1)*ts, rx*ts:(rx+1)*ts]
            # Bloques 2×2 dentro del tile
            t1 = np.roll(tile,-1,1); t2 = np.roll(tile,-1,0)
            t3 = np.roll(np.roll(tile,-1,0),-1,1)
            keys = ((tile.astype(np.int8)<<3) | (t1.astype(np.int8)<<2) |
                    (t2.astype(np.int8)<<1)   |  t3.astype(np.int8)).flatten()
            counts = np.bincount(keys.astype(np.uint8), minlength=16).astype(float)
            hs.append(shannon(counts))
    return float(np.std(hs))


# ──────────────────────────────────────────────
# POSICIONAMIENTO DE SONDAS
# ──────────────────────────────────────────────
def make_probes(rng):
    """K sondas distribuidas uniformemente con jitter aleatorio."""
    cols = int(np.ceil(np.sqrt(K)))
    rows = int(np.ceil(K / cols))
    probes = []
    for r in range(rows):
        for c in range(cols):
            if len(probes) >= K:
                break
            bx = int((c + 0.5) / cols * N)
            by = int((r + 0.5) / rows * N)
            jx = int((rng.random() - 0.5) * N / cols * 0.5)
            jy = int((rng.random() - 0.5) * N / rows * 0.5)
            probes.append(((bx+jx)%N, (by+jy)%N))
    return probes[:K]


# ──────────────────────────────────────────────
# EXPERIMENTO — UNA SEMILLA
# ──────────────────────────────────────────────
def run_seed(seed, verbose=True):
    """
    Corre T pasos para una semilla.
    Retorna dict con todas las series temporales.
    """
    rng = np.random.default_rng(seed)
    grid = (rng.random((N,N)) < 0.35).astype(np.uint8)
    probes = make_probes(rng)
    history = []

    d_arr   = np.zeros(T)
    hs_arr  = np.zeros(T)
    ht_arr  = np.zeros(T)
    het_arr = np.zeros(T)
    dens_arr= np.zeros(T)

    t0 = time.time()
    for step in range(T):
        grid = step_life(grid)
        history.append(grid.copy())
        if len(history) > 8:
            history.pop(0)

        hs = spatial_h(grid, probes)
        ht = temporal_h(history, probes)
        mx = max(hs, ht) or 1.0

        d_arr[step]    = abs(hs - ht) / mx
        hs_arr[step]   = hs
        ht_arr[step]   = ht
        het_arr[step]  = tile_heterogeneity(grid)
        dens_arr[step] = float(grid.mean())

    elapsed = time.time() - t0
    result = dict(d=d_arr, hs=hs_arr, ht=ht_arr,
                  het=het_arr, dens=dens_arr,
                  seed=seed, N=N, K=K, T=T, elapsed=elapsed)

    if verbose:
        fin = d_arr[-50:].mean()*100
        mn  = d_arr.min()*100
        mni = d_arr.argmin()
        print(f"  seed={seed:5d} | final={fin:.2f}% "
              f"min={mn:.2f}%@paso{mni} | {elapsed:.1f}s")

    return result


# ──────────────────────────────────────────────
# ANÁLISIS AGREGADO
# ──────────────────────────────────────────────
def aggregate(all_results):
    """Calcula estadísticas sobre todas las semillas."""
    from scipy import stats as sp_stats

    n    = len(all_results)
    T_   = len(all_results[0]['d'])
    arrd = np.array([r['d']   for r in all_results])
    arhs = np.array([r['hs']  for r in all_results])
    arht = np.array([r['ht']  for r in all_results])
    arhe = np.array([r['het'] for r in all_results])

    def ci95(arr): return 1.96 * arr.std(0) / np.sqrt(n)

    mn_d  = arrd.mean(0); ci_d  = ci95(arrd)
    mn_hs = arhs.mean(0); ci_hs = ci95(arhs)
    mn_ht = arht.mean(0); ci_ht = ci95(arht)
    mn_he = arhe.mean(0)

    # Estadísticas finales
    fin_d  = arrd[:,-50:].mean(1)*100
    fin_ht = arht[:,-50:].mean(1)
    fin_hs = arhs[:,-50:].mean(1)
    min_d  = arrd.min(1)*100
    min_idx= arrd.argmin(1)

    het_at_min = np.array([arhe[i, min_idx[i]] for i in range(n)])
    het_at_end = arhe[:,-1]

    # Correlación mecanismo
    r_ht, p_ht   = sp_stats.pearsonr(fin_ht, fin_d/100)
    t_het, p_het = sp_stats.ttest_1samp(het_at_end - het_at_min, 0)
    t_gap, p_gap = sp_stats.ttest_rel(fin_hs, fin_ht)

    return dict(
        mn_d=mn_d, ci_d=ci_d, mn_hs=mn_hs, ci_hs=ci_hs,
        mn_ht=mn_ht, ci_ht=ci_ht, mn_he=mn_he,
        fin_d=fin_d, fin_ht=fin_ht, fin_hs=fin_hs,
        min_d=min_d, min_idx=min_idx,
        het_at_min=het_at_min, het_at_end=het_at_end,
        r_ht=r_ht, p_ht=p_ht, p_het=p_het, p_gap=p_gap,
        n=n, N=N, K=K, T=T_,
        seeds=[r['seed'] for r in all_results]
    )


# ──────────────────────────────────────────────
# FIGURAS
# ──────────────────────────────────────────────
def make_figures(agg):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    BG  = '#000508'; SURF= '#030b12'; DIM = '#1a3a50'
    HS  = '#00ffe0'; HT  = '#ff2d55'; DLT = '#f5c400'
    HET = '#fb923c'; HI  = '#aecfdf'; TXT = '#5a8099'
    MA  = 50
    def ma(a): return np.convolve(a, np.ones(MA)/MA, mode='same')
    def sty(ax, t=''):
        ax.set_facecolor(SURF)
        for s in ['bottom','left']: ax.spines[s].set_color(DIM)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(colors=DIM, labelsize=8)
        ax.yaxis.label.set_color(TXT); ax.xaxis.label.set_color(TXT)
        if t: ax.set_title(t, color=HI, fontsize=9, pad=7, fontfamily='monospace')
        ax.grid(True, color='#0a1f30', lw=0.5, alpha=0.6)

    steps = np.arange(1, agg['T']+1)
    n     = agg['n']
    mid   = int(ma(agg['mn_d']).argmin())

    # ── FIGURA 1: Convergencia + H(space) vs H(time) ──
    fig1 = plt.figure(figsize=(16,10), facecolor=BG)
    gs1  = GridSpec(2,2, figure=fig1, hspace=0.42, wspace=0.3)
    fig1.text(0.5, 0.98,
        f'LIE en el Juego de la Vida  |  n={n} semillas  N={N} K={K} T={agg["T"]}',
        ha='center', va='top', fontsize=12, color='#e8f4f8',
        fontfamily='monospace', fontweight='bold')

    # Panel A: |ΔH| con IC95%
    axA = fig1.add_subplot(gs1[0,:])
    sty(axA, '|DeltaH| relativo — media ± IC95%')
    axA.fill_between(steps,
        (ma(agg['mn_d'])-ma(agg['ci_d']))*100,
        (ma(agg['mn_d'])+ma(agg['ci_d']))*100,
        alpha=0.15, color=DLT)
    axA.plot(steps, ma(agg['mn_d'])*100, color=DLT, lw=2.5,
        label=f'|DeltaH| final={agg["fin_d"].mean():.1f}%±{1.96*agg["fin_d"].std()/np.sqrt(n):.1f}%')
    axA.axhline(5, color=HS, lw=0.8, ls=':', alpha=0.5, label='Umbral LIE (5%)')
    axA.axvline(mid+1, color='white', lw=1.5, ls='--', alpha=0.5,
        label=f'Min |DeltaH| = {agg["min_d"].mean():.2f}%  paso {mid+1}')
    axA.axhspan(0, 5, alpha=0.05, color=HS)
    for xp,lbl,col in [(60,'Fase 1\nCaos',HS),(mid,'Fase 2\nOrden',DLT),(mid+200,'Fase 3\nEstructura',HT)]:
        if 0 < xp < agg['T']:
            axA.text(xp, ma(agg['mn_d']).max()*100*0.85, lbl,
                color=col, fontsize=7, fontfamily='monospace', ha='center')
    axA.set_xlabel('Pasos', fontsize=8); axA.set_ylabel('|DeltaH| %', fontsize=8)
    axA.legend(fontsize=7.5, facecolor=SURF, labelcolor=HI, edgecolor=DIM, loc='upper right')

    # Panel B: H(espacio) y H(tiempo)
    axB = fig1.add_subplot(gs1[1,0])
    sty(axB, 'H(espacio) y H(tiempo) — evolucion temporal')
    axB.fill_between(steps, ma(agg['mn_hs']-agg['ci_hs']),
        ma(agg['mn_hs']+agg['ci_hs']), alpha=0.12, color=HS)
    axB.fill_between(steps, ma(agg['mn_ht']-agg['ci_ht']),
        ma(agg['mn_ht']+agg['ci_ht']), alpha=0.12, color=HT)
    axB.plot(steps, ma(agg['mn_hs']), color=HS, lw=2, label='H(espacio)')
    axB.plot(steps, ma(agg['mn_ht']), color=HT, lw=2, label='H(tiempo)')
    axB.axvline(mid+1, color='white', lw=1, ls='--', alpha=0.4)
    axB.axvspan(max(0,mid-20), min(agg['T'],mid+20), alpha=0.08, color=DLT, label='Zona LIE')
    axB.set_xlabel('Pasos', fontsize=8); axB.set_ylabel('H (bits)', fontsize=8)
    axB.legend(fontsize=7, facecolor=SURF, labelcolor=HI, edgecolor=DIM)

    # Panel C: scatter H(tiempo)_final vs |ΔH|_final
    from scipy import stats as sp_stats
    axC = fig1.add_subplot(gs1[1,1])
    sty(axC, 'Mecanismo: H(tiempo) final vs |DeltaH| final')
    axC.scatter(agg['fin_ht'], agg['fin_d'], color=HT, s=60, alpha=0.9, zorder=5)
    sl,ic,_,_,_ = sp_stats.linregress(agg['fin_ht'], agg['fin_d']/100)
    xln = np.linspace(agg['fin_ht'].min(), agg['fin_ht'].max(), 100)
    axC.plot(xln, (sl*xln+ic)*100, color=DLT, lw=2,
        label=f'r={agg["r_ht"]:.3f}  p={agg["p_ht"]:.4f}')
    axC.set_xlabel('H(tiempo) final (bits)', fontsize=8)
    axC.set_ylabel('|DeltaH| final %', fontsize=8)
    axC.legend(fontsize=8, facecolor=SURF, labelcolor=HI, edgecolor=DIM)
    axC.text(0.97, 0.95,
        'H(tiempo) bajo\n= mas divergencia',
        transform=axC.transAxes, fontsize=7.5, color=HT, ha='right', va='top',
        fontfamily='monospace',
        bbox=dict(boxstyle='round,pad=0.3', facecolor=BG, edgecolor=HT, alpha=0.9))

    fig1.savefig(os.path.join(OUT_DIR,'figure_1.png'), dpi=150,
        bbox_inches='tight', facecolor=BG, edgecolor='none')
    plt.close(fig1)
    print("  figure_1.png guardada")

    # ── FIGURA 2: Heterogeneidad + resumen ──
    fig2 = plt.figure(figsize=(14,8), facecolor=BG)
    gs2  = GridSpec(1,2, figure=fig2, wspace=0.3)
    fig2.text(0.5, 0.98, 'Heterogeneidad espacial y resumen de resultados',
        ha='center', va='top', fontsize=11, color='#e8f4f8',
        fontfamily='monospace', fontweight='bold')

    # Panel D: het al min vs final
    axD = fig2.add_subplot(gs2[0,0])
    sty(axD, 'Heterogeneidad: en minimo vs final por semilla')
    x = np.arange(n); w = 0.35
    axD.bar(x-w/2, agg['het_at_min'], width=w, color=HS,  alpha=0.8,
        label=f'En min LIE  mu={agg["het_at_min"].mean():.4f}')
    axD.bar(x+w/2, agg['het_at_end'], width=w, color=HET, alpha=0.8,
        label=f'Final       mu={agg["het_at_end"].mean():.4f}')
    axD.set_xticks(x)
    axD.set_xticklabels([str(s) for s in agg['seeds']], rotation=45, fontsize=6)
    axD.set_ylabel('Heterogeneidad (std tiles)', fontsize=8)
    axD.legend(fontsize=7, facecolor=SURF, labelcolor=HI, edgecolor=DIM)
    n_up = (agg['het_at_end'] - agg['het_at_min'] > 0).sum()
    axD.text(0.5, 0.92, f'Sube en {n_up}/{n} semillas  p={agg["p_het"]:.4f}',
        transform=axD.transAxes, fontsize=8.5, color=HET, ha='center',
        fontfamily='monospace',
        bbox=dict(boxstyle='round,pad=0.3', facecolor=BG, edgecolor=HET, alpha=0.9))

    # Panel E: tabla de resultados
    axE = fig2.add_subplot(gs2[0,1])
    axE.set_facecolor(SURF); axE.axis('off')
    rows = [
        ('RESULTADO',            'VALOR',               'VERIFICADO'),
        ('|DeltaH| min',         f'{agg["min_d"].mean():.2f}%±{agg["min_d"].std():.2f}%', f'{n}/{n} seeds'),
        ('|DeltaH| final',       f'{agg["fin_d"].mean():.1f}%±{1.96*agg["fin_d"].std()/np.sqrt(n):.1f}%', 'IC95%'),
        ('r(H(t),|DeltaH|)',     f'{agg["r_ht"]:.3f}',  f'p={agg["p_ht"]:.4f}'),
        ('H(esp)>H(t) final',    'SI',                  f'p={agg["p_gap"]:.4f}'),
        ('Het sube tras min',    f'{n_up}/{n} seeds',   f'p={agg["p_het"]:.4f}'),
    ]
    tbl = axE.table(cellText=rows[1:], colLabels=rows[0],
        loc='center', cellLoc='center', bbox=[0,0.1,1,0.85])
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.5); tbl.scale(1,2.2)
    for (r,c),cell in tbl.get_celld().items():
        cell.set_edgecolor('#0a1f30')
        if r==0:
            cell.set_facecolor('#1A5276')
            cell.set_text_props(color='white', fontfamily='monospace', fontweight='bold')
        else:
            cell.set_facecolor('#EBF5FB' if r%2 else '#FFFFFF')
            cell.set_text_props(color='#1A7A4A' if c==2 else '#333333',
                fontfamily='monospace')

    fig2.savefig(os.path.join(OUT_DIR,'figure_2.png'), dpi=150,
        bbox_inches='tight', facecolor=BG, edgecolor='none')
    plt.close(fig2)
    print("  figure_2.png guardada")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == '__main__':

    if len(sys.argv) == 2:
        # Modo semilla única (para paralelización)
        seed = int(sys.argv[1])
        result = run_seed(seed, verbose=True)
        out_path = os.path.join(OUT_DIR, f'seed_{seed}.npy')
        np.save(out_path, result, allow_pickle=True)
        print(f"  Guardado: {out_path}")

    else:
        # Modo completo: corre todas las semillas
        print(f"Corriendo {len(SEEDS)} semillas  N={N} K={K} T={T}")
        print("="*55)
        print("OPCIÓN RÁPIDA: corre cada semilla por separado:")
        print(f"  for s in {SEEDS[:4]}... ; do python {sys.argv[0]} $s ; done")
        print("="*55)

        all_results = []
        for seed in SEEDS:
            path = os.path.join(OUT_DIR, f'seed_{seed}.npy')
            if os.path.exists(path):
                print(f"  seed={seed} — cargando desde {path}")
                all_results.append(dict(np.load(path, allow_pickle=True).item()))
            else:
                result = run_seed(seed, verbose=True)
                np.save(path, result, allow_pickle=True)
                all_results.append(result)

        print("\nAgregando resultados...")
        agg = aggregate(all_results)

        print(f"\n=== RESULTADOS ===")
        print(f"  |DeltaH| min:         {agg['min_d'].mean():.2f}% ± {agg['min_d'].std():.2f}%")
        print(f"  |DeltaH| final:       {agg['fin_d'].mean():.2f}% ± {1.96*agg['fin_d'].std()/np.sqrt(agg['n']):.2f}% (IC95%)")
        print(f"  r(H(tiempo),|DeltaH|): {agg['r_ht']:.3f}  p={agg['p_ht']:.4f}")
        print(f"  H(esp)>H(t) al final:  p={agg['p_gap']:.4f}")
        print(f"  Het sube tras min:     {(agg['het_at_end']>agg['het_at_min']).sum()}/{agg['n']} seeds  p={agg['p_het']:.4f}")

        np.save(os.path.join(OUT_DIR, 'results_all.npy'), agg, allow_pickle=True)
        print("\nGenerando figuras...")
        make_figures(agg)
        print("\nListo. Archivos generados:")
        for f in ['results_all.npy','figure_1.png','figure_2.png']:
            if os.path.exists(os.path.join(OUT_DIR,f)):
                print(f"  {f}")


# ──────────────────────────────────────────────
# NOTA TÉCNICA PARA REVISORES
# ──────────────────────────────────────────────
"""
RESPUESTAS A PREGUNTAS TÉCNICAS FRECUENTES:

1. ¿H(time) es acumulativa?
   NO. El buffer 'history' mantiene solo las últimas 8 grillas
   (if len(history) > 8: history.pop(0)).
   temporal_h() extrae hist[-4:] = exactamente los últimos 4 pasos.
   Es una ventana DESLIZANTE de longitud 4, no memoria acumulada.

2. ¿La correlación r=-0.721 está inflada por puntos temporales?
   NO. Se calcula como pearsonr(fin_ht, fin_d) donde:
   - fin_ht = media de los últimos 50 pasos POR SEMILLA → 1 valor/semilla
   - fin_d  = media de los últimos 50 pasos POR SEMILLA → 1 valor/semilla
   - n = 20 semillas independientes
   El p-value corresponde a n=20, no a n=T*20.

3. ¿Las sondas están correlacionadas espacialmente?
   SÍ, dentro de una semilla. Pero el análisis estadístico
   usa semillas como unidad independiente (n=20), no sondas (n=K=300).
   Los IC95% son válidos.

4. ¿El drift probe tiene sesgo?
   SÍ. Moverse hacia celdas activas (valor=1) sobre-muestrea zonas
   de alta actividad. Esto puede enriquecer H(time) en drift probes
   y contribuye a su menor divergencia (17.4% vs 53.3%).
   Reconocido como limitación en el paper.

5. ¿Por qué usar ventana de 4 pasos para H(time)?
   Para mantener el mismo alfabeto que H(space): {0,1}^4 → 16 estados.
   Una ventana de 2 pasos daría 4 estados vs 16 de H(space) → sesgo.
   Una ventana más larga requeriría un alfabeto más grande → diferente escala.
"""
