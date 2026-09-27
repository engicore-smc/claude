package cl.horaclima.app;

import android.content.Context;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Descarga todo a la vez y guarda lo que llegue; lo que falle conserva el dato
 * anterior. Bloquea: llamar fuera del hilo principal.
 */
final class Actualizador {

    static final class Resultado {
        boolean climaOk;
        boolean monedasOk;
        boolean ipcOk;
        /** false también si la cuenta del Banco Central no está configurada. */
        boolean tasaOk;
        boolean tasaSinCuenta;
        String tasaError = "";

        boolean todoOk() {
            return climaOk && monedasOk && ipcOk && (tasaOk || tasaSinCuenta);
        }
    }

    private static final Object CANDADO = new Object();

    private Actualizador() {}

    static Resultado actualizar(Context context, int timeoutMs) {
        Context app = context.getApplicationContext();
        ExecutorService hilos = Executors.newFixedThreadPool(4);
        Future<Clima.Lectura[]> clima = hilos.submit(() -> Clima.descargar(Ciudad.TODAS, timeoutMs));
        Future<Indicadores.Monedas> monedas = hilos.submit(() -> Indicadores.monedas(timeoutMs));
        Future<Indicadores.Ipc> ipc = hilos.submit(() -> Indicadores.ipc(timeoutMs));
        Future<BancoCentral.Tasa> tasa = hilos.submit(() -> BancoCentral.hipotecaria(app, timeoutMs));
        hilos.shutdown();

        Resultado res = new Resultado();
        Clima.Lectura[] lecturas = obtener(clima);
        Indicadores.Monedas m = obtener(monedas);
        Indicadores.Ipc i = obtener(ipc);
        BancoCentral.Tasa t = null;
        try {
            t = tasa.get();
            res.tasaSinCuenta = t == null;
        } catch (Exception e) {
            Throwable causa = e.getCause() != null ? e.getCause() : e;
            res.tasaError = causa.getMessage() == null ? "" : causa.getMessage();
        }

        // La app y el widget pueden actualizar a la vez: se lee y escribe en bloque.
        synchronized (CANDADO) {
            Resumen r = Resumen.cargar(app);
            if (lecturas != null) {
                r.lecturas = lecturas;
                r.climaHora = System.currentTimeMillis();
                res.climaOk = true;
            }
            if (m != null) {
                if (!Double.isNaN(m.uf)) {
                    r.uf = m.uf;
                    r.ufFecha = m.ufFecha;
                }
                if (!Double.isNaN(m.dolar)) {
                    r.dolar = m.dolar;
                    r.dolarFecha = m.dolarFecha;
                }
                if (!Double.isNaN(m.euro)) {
                    r.euro = m.euro;
                    r.euroFecha = m.euroFecha;
                }
                r.monedasFuente = m.fuente;
                res.monedasOk = true;
            }
            if (i != null) {
                r.ipc = i.indicador;
                r.ipcHasta = i.hasta;
                res.ipcOk = true;
            }
            if (res.tasaSinCuenta) {
                r.tasa = Double.NaN;
                r.tasaMes = "";
                r.tasaTitulo = "";
            } else if (t != null) {
                r.tasa = t.valor;
                r.tasaMes = t.mes;
                r.tasaTitulo = t.titulo;
                res.tasaOk = true;
            }
            r.guardar(app);
        }
        WidgetResumen.pintar(app);
        return res;
    }

    /** El resultado, o null si falló (sin conexión, respuesta inesperada…). */
    private static <T> T obtener(Future<T> futuro) {
        try {
            return futuro.get();
        } catch (Exception e) {
            return null;
        }
    }
}
