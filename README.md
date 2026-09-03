# Anexos de tensado PLS-CADD

Aplicación web que toma los reportes en Excel de **PLS-CADD**, los filtra y devuelve un
**anexo en Word** con las tablas de tensado listas para copiar y pegar en el informe.

Acceso protegido por una única clave, pensada para un solo usuario.

---

## Qué hace

1. Se suben tres reportes (`.xlsx`, `.xls` o `.csv`).
2. Se detectan las columnas automáticamente (tolera espacios dobles, filas de título y
   encabezados repartidos en dos filas); se puede corregir el mapeo a mano.
3. Se elige el **conductor** (`Cable Load Vert Load (daN/m)`), la **condición** y las
   **temperaturas** a incluir.
4. Se clasifica cada estructura en **anclaje** o **suspensión** (preseleccionado por `_A_` /
   `_S_` en el `Structure Name`, editable).
5. Se muestra una **vista previa** de los tramos antes de procesar.
6. Se genera el **.docx** con una tabla por tramo entre anclajes y su título numerado.

### Reportes de entrada

| Reporte | Columnas que se usan |
|---|---|
| **Flecha y tensión por temperatura** (base principal) | `Span From Str.`, `Span To Str.`, `Span From Set`, `Span To Set`, `Ruling Span (m)`, `Span Vert. Proj. (m)`, `Mid Span Sag (m)`, `Horz. Tension (daN)`, `Wave Time (Sec)`, `Temp. (deg C)`, y opcionalmente una columna de condición / load case |
| **Flecha y tensión (tipo de cable)** | Las mismas de estructura y set, más `Cable Load Vert Load (daN/m)` |
| **Listado de estructuras / staking table** | `Structure Number`, `Structure Name`, y dos columnas de coordenadas |

El tipo de cable se asocia cruzando `(Span From Str., Span To Str., Span From Set, Span To Set)`
entre los dos primeros reportes; el valor de `Cable Load Vert Load` se convierte después en el
filtro que elige el usuario.

### Cómo se arma cada tabla

Una tabla por tramo **entre estructuras de anclaje**. Si hay suspensiones intermedias, se
agregan filas de `Flecha en grampa` y `Tiempo` por cada vano parcial, y la fila de
`Tensión kg` aparece **una sola vez** para todo el tramo (la tensión horizontal es la misma
entre anclajes).

| Columna | Origen |
|---|---|
| Tramo | Estructuras de anclaje de inicio y fin |
| Luz equivalente | `Ruling Span (m)` |
| Control · Estructuras | Cada par de estructuras consecutivas del tramo |
| Control · Vano [m] | `√(Δcoord1² + Δcoord2²)` entre las coordenadas de ambas estructuras |
| Desnivel [m] | `Span Vert. Proj. (m)` |
| Flecha en grampa [m] | `Mid Span Sag (m)` |
| Tiempo [s] | `Wave Time (Sec)` |
| Tensión kg | `Horz. Tension (daN)` × **1.019716** |

> **Coordenadas del vano.** El vano se calcula con Pitágoras sobre las dos columnas que se
> elijan en el mapeo (`Coordenada 1` y `Coordenada 2`). Verifica en la vista previa que el
> resultado sea el esperado: si el vano coincide aproximadamente con `√(luz equivalente² +
> desnivel²)`, las columnas elegidas son las correctas.

---

## Despliegue en Railway

1. Crear un proyecto nuevo desde este repositorio. Railway detecta Python con Nixpacks y usa
   el `startCommand` de `railway.json`.
2. Configurar las variables de entorno:

   | Variable | Obligatoria | Descripción |
   |---|---|---|
   | `APP_PASSWORD` | **sí** | Clave de acceso. Sin ella la app no deja entrar. |
   | `SECRET_KEY` | recomendada | Firma la cookie de sesión. Si falta se genera una al arrancar y las sesiones se cierran en cada redeploy. |
   | `SESSION_MAX_AGE` | no | Duración de la sesión en segundos (8 h por defecto). |
   | `MAX_UPLOAD_MB` | no | Tamaño máximo por archivo (25 MB). |
   | `JOB_TTL_MINUTES` | no | Minutos que los datos siguen en memoria (120). |
   | `MAX_JOBS` | no | Trabajos simultáneos en memoria (6). |
   | `COOKIE_SECURE` | no | `0` solo para desarrollo local por HTTP. |

3. Generar un dominio público. El healthcheck es `/health`.

Un único worker alcanza para el plan de 5 USD: los reportes se procesan en memoria y no se
guarda nada en disco. Los datos subidos se descartan al vencer el TTL o al reiniciar el
contenedor.

---

## Desarrollo local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# reportes de ejemplo para probar la app sin datos reales
python scripts/make_sample_data.py ejemplos

APP_PASSWORD=demo1234 COOKIE_SECURE=0 uvicorn app.main:app --reload --port 8000
```

Tests:

```bash
pytest -q
```

Las pruebas reproducen las dos tablas de referencia (una entre dos anclajes y otra con una
suspensión intermedia) y comparan el texto celda por celda, incluidas las combinaciones de
celdas del Word.

---

## Estructura

```
app/
  main.py         rutas HTTP y API
  auth.py         clave única, cookie firmada y límite de intentos
  config.py       variables de entorno
  store.py        trabajos en memoria con vencimiento
  parsing.py      lectura de XLSX, detección de encabezados y mapeo de columnas
  analysis.py     estructuras, cadenas, tramos entre anclajes y cálculo del vano
  docx_writer.py  generación del Word con celdas combinadas
  templates/      login y aplicación
  static/         estilos y JavaScript
scripts/
  make_sample_data.py   genera reportes de ejemplo
tests/                  pruebas del flujo completo
```
