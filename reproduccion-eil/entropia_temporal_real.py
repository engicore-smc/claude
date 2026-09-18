"""
Entropia temporal REAL de un observador local, frente a la que calcula el paper.

spatial_h() y temporal_h() de spacetime_complete.py son la misma operacion: un
histograma de K muestras, una por sonda, en un instante. Ninguna de las dos es
un promedio temporal. Este script calcula la que si lo es: para cada sonda, la
distribucion de sus palabras de 4 pasos a lo largo de una ventana larga.
"""
import numpy as np
import spacetime_complete as sc

N, WINDOW, BURN = sc.N, 300, 1200

def shannon(c):
    c = c[c > 0]
    return 0.0 if len(c) == 0 else float(-(c / c.sum() * np.log2(c / c.sum())).sum())

def words4(a, b, c, d):
    return (a.astype(int) << 3) | (b.astype(int) << 2) | (c.astype(int) << 1) | d.astype(int)

def analyse(seed):
    rng = np.random.default_rng(seed)
    g = (rng.random((N, N)) < 0.35).astype(np.uint8)
    probes = sc.make_probes(rng)
    px = np.array([p[0] for p in probes]); py = np.array([p[1] for p in probes])

    for _ in range(BURN):
        g = sc.step_life(g)

    trace = np.zeros((WINDOW, len(probes)), dtype=np.uint8); grids = []
    for t in range(WINDOW):
        g = sc.step_life(g); trace[t] = g[py, px]; grids.append(g.copy())

    # (a) H(tiempo) del paper: palabras de 4 pasos agrupadas ENTRE sondas
    pooled = [shannon(np.bincount(words4(trace[t-4], trace[t-3], trace[t-2], trace[t-1]),
                                  minlength=16).astype(float)) for t in range(4, WINDOW)]
    # (b) H(tiempo) real: palabras de 4 pasos de cada sonda A LO LARGO DEL TIEMPO
    per = np.array([shannon(np.bincount(
        words4(s[:-3], s[1:-2], s[2:-1], s[3:]), minlength=16).astype(float))
        for s in trace.T.astype(int)])
    # (c) H(espacio) en los mismos instantes
    spat = [shannon(np.bincount(words4(gr[py, px], gr[py, (px+1) % N],
                                       gr[(py+1) % N, px], gr[(py+1) % N, (px+1) % N]),
                                minlength=16).astype(float)) for gr in grids[4:]]
    return np.mean(spat), np.mean(pooled), per

if __name__ == '__main__':
    print(f"Regimen tardio (tras {BURN} pasos), ventana de {WINDOW} pasos, K={sc.K} sondas\n")
    for seed in [42, 137, 271, 314, 999]:
        sp, pool, per = analyse(seed)
        print(f"semilla {seed}:")
        print(f"   H(espacio) ensemble                 = {sp:.3f} bits")
        print(f"   H(tiempo) del paper (pool sondas)   = {pool:.3f} bits")
        print(f"   H(tiempo) REAL (por obs., sobre t)  = {per.mean():.3f} bits"
              f"   mediana {np.median(per):.3f}")
        print(f"   sondas con H temporal == 0          = {(per < 1e-9).sum()}/{len(per)}\n")
