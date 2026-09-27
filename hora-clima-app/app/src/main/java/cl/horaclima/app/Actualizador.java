package cl.horaclima.app;

import android.content.Context;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Descarga temperatura y euro a la vez y guarda lo que llegue. Bloquea: llamar fuera del hilo principal. */
final class Actualizador {

    static final class Resultado {
        boolean climaOk;
        boolean euroOk;
    }

    private static final Object CANDADO = new Object();

    private Actualizador() {}

    static Resultado actualizar(Context context, int timeoutMs) {
        Context app = context.getApplicationContext();
        ExecutorService hilos = Executors.newFixedThreadPool(2);
        Future<Clima.Lectura[]> clima = hilos.submit(() -> Clima.descargar(Ciudad.TODAS, timeoutMs));
        Future<Euro.Cotizacion> euro = hilos.submit(() -> Euro.descargar(timeoutMs));
        hilos.shutdown();

        Clima.Lectura[] lecturas = null;
        Euro.Cotizacion cotizacion = null;
        try {
            lecturas = clima.get();
        } catch (Exception e) {
            // Sin conexión o respuesta inesperada: se mantiene el dato anterior.
        }
        try {
            cotizacion = euro.get();
        } catch (Exception e) {
            // Ídem.
        }

        Resultado resultado = new Resultado();
        // La app y el widget pueden actualizar a la vez: se lee y escribe en bloque.
        synchronized (CANDADO) {
            Resumen r = Resumen.cargar(app);
            if (lecturas != null) {
                r.lecturas = lecturas;
                r.climaHora = System.currentTimeMillis();
                resultado.climaOk = true;
            }
            if (cotizacion != null) {
                r.euro = cotizacion.valor;
                r.euroFuente = cotizacion.fuente;
                r.euroFecha = cotizacion.fecha;
                resultado.euroOk = true;
            }
            r.guardar(app);
        }
        WidgetResumen.pintar(app);
        return resultado;
    }
}
