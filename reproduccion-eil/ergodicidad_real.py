"""
El test de ergodicidad que el paper deberia haber hecho.

La clave: usar EL MISMO observable y promediarlo de dos maneras.
El array espacio-tiempo se recorre en dos direcciones:
   - escaneo ESPACIAL : fijo t, recorro todas las celdas  -> P_espacio
   - escaneo TEMPORAL : fijo la celda, recorro todos los t -> P_tiempo
Si la medida espacio-temporal es ergodica bajo ambos shifts, coinciden.
Eso es literalmente la hipotesis: "lo que pasa en el tiempo aqui, pasa
en el espacio alla".
"""
import numpy as np

W = 4  # longitud de la palabra

def words(seq_axis0):
    """seq (L, M) uint8 -> palabras de W pasos a lo largo del eje 0."""
    L = seq_axis0.shape[0]
    k = np.zeros((L - W + 1, seq_axis0.shape[1]), dtype=int)
    for i in range(W):
        k = (k << 1) | seq_axis0[i:L - W + 1 + i].astype(int)
    return k

def dist(keys):
    c = np.bincount(keys.ravel(), minlength=2**W).astype(float)
    return c / c.sum()

def H(p):
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())

def tv(p, q):
    return 0.5 * np.abs(p - q).sum()

# ---------- 1D: CA elemental ----------
def run_eca(rule, N=4000, T=4000, burn=1000, seed=0):
    rng = np.random.default_rng(seed)
    s = (rng.random(N) < 0.5).astype(np.uint8)
    tbl = np.array([(rule >> i) & 1 for i in range(8)], dtype=np.uint8)
    out = np.zeros((T, N), dtype=np.uint8)
    for t in range(burn + T):
        idx = (np.roll(s, 1).astype(int) << 2) | (s.astype(int) << 1) | np.roll(s, -1).astype(int)
        s = tbl[idx]
        if t >= burn:
            out[t - burn] = s
    return out

# ---------- 2D: Life ----------
def run_life(N=300, T=2000, burn=1500, seed=0, dens=0.35):
    rng = np.random.default_rng(seed)
    g = (rng.random((N, N)) < dens).astype(np.uint8)
    out = np.zeros((T, N * N), dtype=np.uint8)
    for t in range(burn + T):
        nb = sum(np.roll(np.roll(g, i, 0), j, 1)
                 for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0))
        g = ((g == 1) & ((nb == 2) | (nb == 3)) | (g == 0) & (nb == 3)).astype(np.uint8)
        if t >= burn:
            out[t - burn] = g.ravel()
    return out

def report(name, st, n_cells=400, seed=0):
    """st: (T, M) array espacio-tiempo."""
    T, M = st.shape
    rng = np.random.default_rng(seed)
    # escaneo ESPACIAL: en cada instante, todas las celdas
    tt = rng.choice(T - W, size=min(200, T - W), replace=False)
    P_space = dist(np.stack([words(st[t:t + W])[0] for t in tt]))
    # escaneo TEMPORAL: por celda, a lo largo de todo el tiempo
    cells = rng.choice(M, size=min(n_cells, M), replace=False)
    P_time = np.stack([dist(words(st[:, [c]])) for c in cells])
    tvs = np.array([tv(P_space, p) for p in P_time])
    print(f"\n{name}")
    print(f"   H(P_espacio)            = {H(P_space):.3f} bits")
    print(f"   H(P_tiempo) por celda   = {np.mean([H(p) for p in P_time]):.3f} bits"
          f"   (mediana {np.median([H(p) for p in P_time]):.3f})")
    print(f"   distancia TV(espacio, tiempo) : mediana {np.median(tvs):.3f}"
          f"   p90 {np.percentile(tvs,90):.3f}")
    print(f"   celdas con TV < 0.10    = {(tvs<0.10).sum()}/{len(tvs)}"
          f"   -> {'ERGODICO' if np.median(tvs)<0.10 else 'NO ergodico'}")

if __name__ == '__main__':
    print("Mismo observable (palabra de 4 pasos), promediado en espacio vs en tiempo.")
    print("Si la hipotesis es cierta, las dos distribuciones coinciden (TV -> 0).")
    report("Rule 30  (1D, caotico, entropia positiva)", run_eca(30))
    report("Rule 110 (1D, clase IV)",                   run_eca(110))
    report("Life     (2D, toro 300x300)",               run_life())
