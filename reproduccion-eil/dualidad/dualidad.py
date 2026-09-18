"""
CASO B: region espacial finita, tiempo infinito.
  "Todo ocurre a lo largo del tiempo -> la historia se puede reconstruir."

Se mide cuantos de los 2^9 = 512 patrones posibles llega a VISITAR una ventana
acotada a lo largo de T pasos, y en cuantos pasos deja de ver cosas nuevas.

Se contrasta Life (irreversible) con Life de segundo orden
   s(t+1) = life(s(t)) XOR s(t-1)
que es reversible por construccion: s(t-1) = life(s(t)) XOR s(t+1).
"""
import numpy as np

def life(g):
    nb = sum(np.roll(np.roll(g, i, 0), j, 1)
             for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0))
    return ((g == 1) & ((nb == 2) | (nb == 3)) | (g == 0) & (nb == 3)).astype(np.uint8)

def eca(rule):
    tbl = np.array([(rule >> i) & 1 for i in range(8)], dtype=np.uint8)
    def f(s):
        return tbl[(np.roll(s, 1).astype(int) << 2) | (s.astype(int) << 1) | np.roll(s, -1).astype(int)]
    return f

def coverage(sampler, T, label, alpha=512):
    seen = set(); first_new = 0; curve = []
    for t in range(T):
        k = sampler(t)
        if k not in seen:
            seen.add(k); first_new = t
        if t % (T // 50) == 0:
            curve.append(len(seen))
    print(f"   {label:38s} {len(seen):>4}/{alpha}  ({len(seen)/alpha:6.1%})"
          f"   ultimo patron nuevo en el paso {first_new:,}")
    return len(seen)

N, T = 200, 100_000
rng = np.random.default_rng(7)

print(f"CASO B — ¿cubre una ventana acotada el espacio de patrones en T={T:,} pasos?")
print("   ventana de 9 celdas -> 512 patrones posibles\n")

# --- Life irreversible ---
g = (rng.random((N, N)) < 0.35).astype(np.uint8)
state = {'g': g}
def s_life(t):
    state['g'] = life(state['g'])
    w = state['g'][100:103, 100:103].ravel()
    return int((w.astype(int) << np.arange(9)).sum())
coverage(s_life, T, "Life 2D (irreversible)")

# --- Life de segundo orden, reversible ---
prev = (rng.random((N, N)) < 0.35).astype(np.uint8)
cur = (rng.random((N, N)) < 0.35).astype(np.uint8)
st2 = {'p': prev, 'c': cur}
def s_life2(t):
    nxt = life(st2['c']) ^ st2['p']
    st2['p'], st2['c'] = st2['c'], nxt
    w = st2['c'][100:103, 100:103].ravel()
    return int((w.astype(int) << np.arange(9)).sum())
coverage(s_life2, T, "Life 2D de 2do orden (REVERSIBLE)")

# --- Rule 30, 1D caotico ---
f30 = eca(30)
s = (rng.random(4000) < 0.5).astype(np.uint8)
st3 = {'s': s}
def s_r30(t):
    st3['s'] = f30(st3['s'])
    w = st3['s'][2000:2009]
    return int((w.astype(int) << np.arange(9)).sum())
coverage(s_r30, T, "Rule 30 1D (caotico)")

# --- reversibilidad explicita: ida y vuelta ---
print("\nVerificacion de reversibilidad (Life de 2do orden, 64x64, 500 pasos):")
p0 = (rng.random((64, 64)) < 0.4).astype(np.uint8)
c0 = (rng.random((64, 64)) < 0.4).astype(np.uint8)
p, c = p0.copy(), c0.copy()
for _ in range(500):
    p, c = c, life(c) ^ p
for _ in range(500):                      # marcha atras
    c, p = p, life(p) ^ c
print(f"   estado inicial recuperado exactamente: {np.array_equal(p, p0) and np.array_equal(c, c0)}")
print("   -> con dinamica inyectiva, la instantanea SI contiene toda la historia.")
