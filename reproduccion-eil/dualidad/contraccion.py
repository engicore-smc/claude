"""
CASO A de la hipotesis: espacio infinito, instantanea congelada.
  "Todo ocurre a la vez -> la historia se puede reconstruir."

Para que una instantanea contenga la historia, la dinamica tiene que ser
INYECTIVA: dos pasados distintos no pueden dar el mismo presente. Si F no es
inyectiva, la historia se borra y ninguna cantidad de espacio la recupera.

Medimos |F(X)| / |X| exhaustivamente sobre un toro NxN.
"""
import numpy as np

def life_step_batch(bits):
    """bits: (M, N, N) uint8 -> siguiente estado."""
    nb = sum(np.roll(np.roll(bits, i, 1), j, 2)
             for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0))
    return ((bits == 1) & ((nb == 2) | (nb == 3)) | (bits == 0) & (nb == 3)).astype(np.uint8)

def unpack(codes, N):
    sh = np.arange(N * N, dtype=np.uint64)
    return ((codes[:, None] >> sh) & 1).astype(np.uint8).reshape(-1, N, N)

def pack(bits, N):
    sh = np.arange(N * N, dtype=np.uint64)
    return (bits.reshape(len(bits), -1).astype(np.uint64) << sh).sum(1)

def contraction(N, chunk=1 << 21):
    total = 1 << (N * N)
    img = set()
    for start in range(0, total, chunk):
        codes = np.arange(start, min(start + chunk, total), dtype=np.uint64)
        img.update(pack(life_step_batch(unpack(codes, N)), N).tolist())
    return total, len(img)

if __name__ == '__main__':
    print("CASO A — ¿es inyectiva la dinamica? (Life, toro NxN, exhaustivo)\n")
    print(f"{'N':>3} {'estados':>12} {'imagen |F(X)|':>14} {'superv.':>9} {'bits perdidos':>14}")
    for N in (3, 4, 5):
        tot, im = contraction(N)
        print(f"{N:>3} {tot:>12,} {im:>14,} {im/tot:>8.3%} {np.log2(tot/im):>13.2f}")
    print("\n  'superv.' = fraccion de estados que tienen al menos un predecesor.")
    print("  El resto son Jardines del Eden: presentes que ningun pasado produce.")

    # colapso iterado: cuanto queda del espacio de estados tras n pasos
    N = 4; tot = 1 << (N * N)
    cur = np.arange(tot, dtype=np.uint64)
    print(f"\nColapso iterado del espacio de estados (N={N}, {tot:,} estados):")
    for step in range(1, 13):
        cur = np.unique(pack(life_step_batch(unpack(cur, N)), N))
        print(f"   tras {step:2d} pasos: {len(cur):>7,} estados"
              f"  ({len(cur)/tot:7.3%})   informacion superviviente: "
              f"{np.log2(len(cur)):.1f} de {N*N} bits")
