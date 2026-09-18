# La dualidad espacio-infinito ↔ tiempo-infinito

Hipótesis a testear:

- **Caso A** — espacio infinito, instantánea congelada: «todo ocurre a la vez»,
  luego la historia se puede reconstruir del snapshot.
- **Caso B** — región finita, tiempo infinito: «todo ocurre a lo largo del
  tiempo», luego la historia se puede reconstruir del registro temporal.

## Resultados

**Caso A — ¿es inyectiva la dinámica?** (`contraccion.py`, exhaustivo)

| N | estados | imagen \|F(X)\| | con predecesor | bits destruidos/paso |
|---|---|---|---|---|
| 3 | 512 | 128 | 25,0% | 2,00 |
| 4 | 65 536 | 17 879 | 27,3% | 1,87 |
| 5 | 33 554 432 | 8 520 996 | 25,4% | 1,98 |

Tres de cada cuatro configuraciones son **Jardines del Edén**: presentes que
ningún pasado produce. Iterando en N=4, el espacio de estados colapsa de 65 536
a 1 245 (1,9%) en 9 pasos y ahí se queda. Life **borra** la historia, ~2 bits
por paso. Ninguna cantidad de espacio la recupera: el borrado ocurre local y
simultáneamente en todas partes.

**Caso B — ¿cubre una ventana acotada el espacio de patrones?**
(`dualidad.py`, ventana de 9 celdas = 512 patrones, T=100 000)

| sistema | patrones vistos | último patrón nuevo |
|---|---|---|
| Life 2D (irreversible) | **116/512** (22,7%) | paso 2 593 |
| Life 2D de 2º orden (**reversible**) | **512/512** | paso 5 942 |
| Rule 30 1D (caótico) | **512/512** | paso 3 547 |

Life deja de ver patrones nuevos en el paso 2 593 y los siguientes 97 000 pasos
no aportan nada.

## Conclusión

Los dos casos **no son dos rutas independientes**. Aciertan y fallan juntos, y
lo que decide es la misma propiedad: **si la dinámica preserva información**.

- Life de 2º orden (inyectiva): Caso A ✅ (ida y vuelta de 500 pasos recupera el
  inicial exactamente) y Caso B ✅ (512/512).
- Life (no inyectiva): Caso A ❌ (75% Jardines del Edén) y Caso B ❌ (116/512).

El congelamiento de Life, su no-inyectividad y la no-cobertura de la ventana son
**el mismo hecho visto tres veces**: el espacio de estados colapsa a 1 245
atractores, y eso es exactamente lo que ve la ventana local.

Correr: `python3 contraccion.py` (~2 min) · `python3 dualidad.py` (~3 min)
