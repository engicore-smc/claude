"""
Reconstruction of E4 (fixed), E5 (drift), E6 (random walk) and the
asymmetric-alphabet comparison. These are NOT in spacetime_complete.py;
the implementation follows the prose in spacetime_es.docx Sec. 3.2.
  E4/E5/E6: N=100, K=150, T=500, 10 seeds.
  drift  = probe moves to the neighbouring cell with the most live neighbours.
  rwalk  = probe takes a uniformly random step in one of 8 directions.
"""
import numpy as np, sys
from scipy import stats as sp

N, K, T = 100, 150, 500
SEEDS = [42, 137, 271, 314, 999, 17, 88, 256, 512, 1024]

def step_life(g):
    nb = sum(np.roll(np.roll(g, i, 0), j, 1)
             for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0))
    return ((g == 1) & ((nb == 2) | (nb == 3)) | (g == 0) & (nb == 3)).astype(np.uint8)

def neighbour_count(g):
    return sum(np.roll(np.roll(g, i, 0), j, 1)
               for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0))

def shannon(counts):
    c = counts[counts > 0]
    if len(c) == 0: return 0.0
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())

def spatial_h(g, px, py):
    x1, y1 = (px + 1) % N, (py + 1) % N
    key = (g[py, px].astype(int) << 3) | (g[py, x1].astype(int) << 2) | \
          (g[y1, px].astype(int) << 1) | g[y1, x1].astype(int)
    return shannon(np.bincount(key, minlength=16).astype(float))

def temporal_h(trace, w):
    """trace: (w, K) array of the values each probe SAW on its last w steps."""
    key = np.zeros(trace.shape[1], dtype=int)
    for i in range(w):
        key = (key << 1) | trace[i].astype(int)
    return shannon(np.bincount(key, minlength=2 ** w).astype(float))

DIRS = np.array([(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0)])

def run(seed, mode, w=4):
    rng = np.random.default_rng(seed)
    g = (rng.random((N, N)) < 0.35).astype(np.uint8)
    px = rng.integers(0, N, K); py = rng.integers(0, N, K)
    trace = []
    d = np.zeros(T)
    for t in range(T):
        g = step_life(g)
        if mode == 'drift':
            nb = neighbour_count(g)
            cand = (py[None, :] + DIRS[:, 0:1]) % N, (px[None, :] + DIRS[:, 1:2]) % N
            best = nb[cand[0], cand[1]].argmax(0)
            py = (py + DIRS[best, 0]) % N; px = (px + DIRS[best, 1]) % N
        elif mode == 'rwalk':
            k = rng.integers(0, 8, K)
            py = (py + DIRS[k, 0]) % N; px = (px + DIRS[k, 1]) % N
        trace.append(g[py, px].copy())
        if len(trace) > w: trace.pop(0)
        hs = spatial_h(g, px, py)
        ht = temporal_h(np.array(trace), w) if len(trace) == w else 0.0
        d[t] = abs(hs - ht) / (max(hs, ht) or 1.0)
    return d

def summarise(label, vals):
    m, ci = vals.mean(), 1.96 * vals.std() / np.sqrt(len(vals))
    print(f"  {label:34s} {m:5.1f}% +- {ci:.1f}%   (per-seed: "
          + " ".join(f"{v:.0f}" for v in vals) + ")")
    return m, ci

if __name__ == '__main__':
    print(f"E4/E5/E6 reconstruction  N={N} K={K} T={T} n={len(SEEDS)} seeds\n")
    out = {}
    for mode, lbl, exp in [('fixed', 'E4 fixed probes', 53.3),
                           ('drift', 'E5 drift probes', 17.4),
                           ('rwalk', 'E6 random walk', 64.1)]:
        vals = np.array([run(s, mode)[-50:].mean() * 100 for s in SEEDS])
        m, ci = summarise(f"{lbl}  (paper {exp}%)", vals)
        out[mode] = vals
    red = 100 * (1 - out['drift'].mean() / out['fixed'].mean())
    print(f"\n  drift reduction vs fixed: {red:.0f}%   (paper claims 67%)")

    print("\nAsymmetric alphabet (H(time) over 2 steps = 4 states vs 16 for H(space)):")
    a = np.array([run(s, 'fixed', w=2)[-50:].mean() * 100 for s in SEEDS])
    summarise("asymmetric (w=2)", a)
    infl = 100 * (a.mean() - out['fixed'].mean()) / a.mean()
    print(f"  symmetric reduces divergence by {infl:.1f}%  (paper claims 20.8%)")
