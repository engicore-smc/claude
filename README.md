# Anexos de tensado PLS-CADD

Toma los reportes en Excel de **PLS-CADD**, los filtra y devuelve un **anexo en Word** con las
tablas de tensado listas para copiar y pegar en el informe.

Hay dos formas de usarlo sobre el mismo núcleo de cálculo:

| | Para qué sirve | Cómo se ejecuta |
|---|---|---|
| **Aplicación web** | Control total: mapeo de columnas, temperaturas, tipo de cada estructura, formato del documento | `uvicorn app.main:app` |
| **Bot de Telegram** | Lo rápido: mandar los tres XLSX, elegir el conductor y recibir el anexo | `python -m bot.main` |

El cálculo vive en `app/` (`parsing`, `analysis`, `docx_writer`) y las dos interfaces lo comparten,
así que ambas producen exactamente el mismo documento.

---

## Qué hace

1. Se suben tres reportes (`.xlsx`, `.xls` o `.csv`).
2. Se detectan las columnas automáticamente (tolera espacios dobles, filas de título y
   encabezados repartidos en dos filas); se puede corregir el mapeo a mano.
3. Se elige el **conductor** (`Cable Load Vert Load (daN/m)`) y las **temperaturas**.
4. Se revisan los **tramos**: se marcan con una casilla los que van al anexo (por defecto todos) y
   el tipo de cada estructura (**anclaje** / **suspensión**) se cambia con un clic sobre ella.
5. Se genera el **.docx** con una tabla por tramo entre anclajes y su título numerado.

El documento sale en **tabloide horizontal (11×17″)** para que ningún valor se parta en dos
líneas: los anchos de columna se calculan a partir del texto más largo de cada una y se aplican
iguales a todas las tablas. El tamaño y la orientación se pueden cambiar; si el contenido no
entra, las columnas se reducen proporcionalmente.

Los títulos se insertan como **títulos de Word** (estilo `Título`/`Caption` con un campo
`SEQ Tabla`), igual que con *Referencias → Insertar título*. Word los numera solo y aparecen en
*Insertar → Referencia cruzada* para citarlos desde el texto del informe.

El número entero va dentro del campo, sin texto literal alrededor, así que la numeración es
automática de punta a punta: si se inserta o borra una tabla, Word renumera el resto. El estilo
`Título` de Word es azul por defecto; aquí se fuerza a **negro**.

«Primera tabla n.º» controla el arranque:

- Dejado en **1** (por defecto) el campo va sin reinicio, de modo que al pegar las tablas en un
  informe que ya tiene tablas, Word continúa la numeración de ese informe.
- Con otro valor, la primera tabla emite `SEQ Tabla \r N` y la cuenta arranca en `N`.

Cada reporte corresponde a **una condición** (`Initial RS`, `Final`, …): para otra condición se
sube el reporte de esa condición. El texto se toma del reporte y se usa en el título de las
tablas.

### Reportes de entrada

| Reporte | Columnas que se usan |
|---|---|
| **Reporte tensado** (base principal) | `Span From Str.`, `Span To Str.`, `Span From Set`, `Span To Set`, `Sec. No.`, `Ruling Span (m)`, `Span Length (m)`, `Span Vert. Proj. (m)`, `Mid Span Sag (m)`, `Horz. Tension (daN)`, `Wave Time (Sec)`, `Temp. (deg C)`, `Cable Condition` |
| **Reporte flecha y tensión** | Las mismas de estructura y set, más `Cable Load Vert Load (daN/m)` y `Weather Case Description` |
| **Reporte Staking table** | `Structure Number`, `Structure Name`, `Structure Description`, `X Easting (m)`, `Y Northing (m)` |

El tipo de cable se asocia cruzando `(Span From Str., Span To Str., Span From Set, Span To Set)`
entre los dos primeros reportes; el valor de `Cable Load Vert Load` se convierte después en el
filtro que elige el usuario.

> **Casos de clima.** `Cable Load Vert Load` cambia con hielo o viento, así que no siempre
> identifica al cable. Por defecto se toma el **menor valor de cada vano**, que es el peso propio
> del conductor; también se puede fijar un caso de clima concreto.

### Cómo se detectan los tramos

Prioridad, de más a menos fiable:

1. **`Sec. No.`** del reporte principal: PLS-CADD ya agrupa los vanos en secciones de tensado,
   que son justamente los tramos entre anclajes. Los extremos de cada sección son anclajes y las
   estructuras interiores, suspensiones.
2. **`_A_` / `_S_`** en el nombre del archivo `.stk` de `Structure Name` (se ignora la ruta, para
   que una carpeta llamada `a` no se lea como `_A_`).
3. Las palabras «anclaje» / «suspensión» en `Structure Description`.

Si el nombre y las secciones no coinciden, manda el nombre y se avisa en la vista previa. El tipo
de cualquier estructura se puede cambiar con un clic: marcar una intermedia como anclaje **parte**
el tramo, y marcar un extremo como suspensión **une** los dos tramos vecinos.

Cada tramo lleva una casilla para decidir si entra en el anexo. La selección se identifica por los
extremos del tramo, no por su posición, así que cambiar el tipo de una estructura no descoloca lo
que ya estaba marcado; los tramos que aparecen nuevos entran marcados. En el bot de Telegram se
generan siempre todos.

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
| Tensión [kg] | `Horz. Tension (daN)` × **1.019716** |

> **Coordenadas del vano.** El vano se calcula con Pitágoras sobre `X Easting (m)` e
> `Y Northing (m)`, igual que la fórmula de Excel original. Si el reporte trae `Span Length (m)`,
> se compara con el vano calculado y se avisa cuando difieren, lo que delata columnas de
> coordenadas mal asignadas.

---

## Bot de Telegram

Pide lo mínimo: los tres reportes y el conductor. Todo lo demás usa los valores por defecto
(todas las temperaturas, tipos de estructura detectados automáticamente, tabloide horizontal).

1. Crear el bot con [@BotFather](https://t.me/BotFather) y copiar el token, o reutilizar uno que
   ya exista: `/mybots` → elegir el bot → **API Token**.
2. Enviarle los tres XLSX **en cualquier orden**: se reconocen por sus columnas, no por el nombre
   del archivo.
3. Elegir el conductor en los botones que aparecen.
4. Recibir el `.docx`.

Comandos: `/nuevo` empieza de cero · `/estado` muestra qué falta · `/conductor` vuelve a elegir
cable sin resubir nada · `/salir` cierra la sesión.

### Acceso

Hay que definir **al menos una** de estas dos variables; sin ninguna el bot se niega a arrancar,
para que no quede abierto a cualquiera:

| Variable | Descripción |
|---|---|
| `TELEGRAM_ALLOWED_USERS` | IDs de Telegram autorizados, separados por comas. Es lo más seguro y sobrevive a los reinicios. |
| `BOT_PASSWORD` | Clave compartida. Se desbloquea con `/clave TU_CLAVE` y dura hasta que se reinicie el contenedor. |

Si escribes al bot sin autorización, te responde con tu ID de Telegram para que puedas añadirlo a
`TELEGRAM_ALLOWED_USERS`. Para averiguar tu ID la primera vez: despliega con un `BOT_PASSWORD`
cualquiera, escríbele `/start` y te contestará con tu ID.

### Reutilizar un bot que ya existe

Funciona sin más, con dos avisos:

- **Un token, un solo proceso.** Telegram solo admite un consumidor de `getUpdates` por token: si el
  bot anterior sigue corriendo en otro sitio, los dos se quitarán los mensajes o dará error 409.
  Hay que apagar el anterior o usar un bot distinto.
- **Webhook.** Si el bot tenía un webhook configurado, el long polling no arrancaría. Al iniciar se
  borra automáticamente (`deleteWebhook`), así que no hay que hacer nada.

El menú de comandos también se registra solo al arrancar; no hace falta el `/setcommands` de
BotFather.

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

### El bot, como segundo servicio

El bot no escucha en ningún puerto (usa long polling), así que va en un servicio aparte del mismo
repositorio:

1. **New → GitHub Repo**, el mismo repositorio y la misma rama.
2. En **Settings → Deploy → Custom Start Command**, poner `python -m bot.main`. (También se puede
   apuntar **Config-as-code** a `railway.bot.json`, que ya trae ese arranque.)
3. En **Variables**: `TELEGRAM_TOKEN` y `TELEGRAM_ALLOWED_USERS` o `BOT_PASSWORD`. Este servicio no
   necesita `APP_PASSWORD` ni dominio público.

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
bot/
  main.py         comandos y handlers de Telegram
  flow.py         lógica del bot, sin nada de Telegram (identifica reportes, arma respuestas)
  auth.py         lista de IDs y clave compartida
  config.py       variables de entorno del bot
scripts/
  make_sample_data.py   genera reportes de ejemplo
tests/                  pruebas de los dos frontales
```
