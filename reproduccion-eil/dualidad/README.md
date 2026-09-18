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

## Conclusión — la dualidad NO se sostiene

Una versión anterior de este README afirmaba que los dos casos «aciertan y fallan
juntos», controlados ambos por la inyectividad. **Eso es falso.** Existen las
cuatro combinaciones:

| sistema | Caso A (instantánea) | Caso B (ventana en el tiempo) |
|---|---|---|
| Life 2D | ❌ no inyectiva | ❌ 116/512 |
| Life 2º orden (genérico) | ✅ reversible | ✅ 512/512 |
| **Rule 30** | ❌ **no inyectiva** (pierde 0,04–0,15 bits/paso) | ✅ **512/512** |
| **Life 2º orden desde un still-life** | ✅ **reversible** | ❌ **2/512** |

Los dos últimos son los contraejemplos. Rule 30 no es inyectiva —lo comprobé
exhaustivamente sobre anillos de 10, 14 y 18 celdas— y aun así su ventana cubre
todo el espacio de patrones. Y Life de 2º orden arrancado desde un still-life con
`prev == cur` es perfectamente reversible y su ventana ve 2 patrones de 512.

La razón por la que no pueden ser equivalentes es de tipo, no de grado:

- El **Caso A** es una propiedad del **mapa** F: ¿es inyectivo? Eso es
  exactamente la definición de reversibilidad.
- El **Caso B** es una propiedad de la **órbita**: ¿la proyección de *esta*
  trayectoria sobre una ventana cubre el espacio de patrones? Depende de la
  condición inicial, no solo de la regla.

Una propiedad del mapa y una propiedad de una órbita concreta no pueden ser la
misma condición. Que coincidieran en los tres primeros sistemas que probé fue
coincidencia de muestreo.

## Lo que sí queda en pie

Las mediciones individuales son correctas y reproducibles: Life destruye ~2
bits/paso, el 75% de las configuraciones son Jardines del Edén, el espacio de
estados colapsa a 1.245 atractores en 9 pasos, y una ventana local satura en el
paso 2.593. Lo que no se sostiene es la síntesis en forma de dualidad.

Correr: `python3 contraccion.py` (~2 min) · `python3 dualidad.py` (~3 min)
