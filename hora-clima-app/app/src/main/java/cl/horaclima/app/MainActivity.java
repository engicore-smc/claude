package cl.horaclima.app;

import android.app.Activity;
import android.graphics.Insets;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.TextView;

import java.text.DateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Pantalla única: la hora en Chile y España (la dan los TextClock del layout,
 * con la zona horaria del teléfono) y la temperatura de tres ciudades.
 */
public class MainActivity extends Activity {

    private static final Ciudad[] CIUDADES = {
            new Ciudad("Chillán", "Ñuble, Chile", -36.6061, -72.1039),
            new Ciudad("San Nicolás", "Ñuble, Chile", -36.5000, -72.2167),
            new Ciudad("Galapagar", "Madrid, España", 40.5786, -4.0039),
    };

    private static final String ZONA_CHILE = "America/Santiago";
    private static final String ZONA_ESPANA = "Europe/Madrid";

    /** Cada cuánto se vuelve a pedir la temperatura mientras la app está abierta. */
    private static final long INTERVALO_MS = 15 * 60 * 1000L;

    private final ExecutorService red = Executors.newSingleThreadExecutor();
    private final Handler principal = new Handler(Looper.getMainLooper());
    private final Runnable refrescoPeriodico = this::actualizar;
    private final View[] tarjetas = new View[CIUDADES.length];

    private TextView estado;
    private TextView diferencia;
    private boolean cargando;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Android 15 dibuja la app bajo las barras del sistema: se deja su espacio.
        View raiz = findViewById(R.id.raiz);
        raiz.setOnApplyWindowInsetsListener((v, insets) -> {
            Insets barras = insets.getInsets(WindowInsets.Type.systemBars());
            v.setPadding(barras.left, barras.top, barras.right, barras.bottom);
            return WindowInsets.CONSUMED;
        });

        estado = findViewById(R.id.estado);
        diferencia = findViewById(R.id.diferencia);

        ViewGroup contenedor = findViewById(R.id.ciudades);
        LayoutInflater inflater = getLayoutInflater();
        for (int i = 0; i < CIUDADES.length; i++) {
            View tarjeta = inflater.inflate(R.layout.item_ciudad, contenedor, false);
            ((TextView) tarjeta.findViewById(R.id.nombre)).setText(CIUDADES[i].nombre);
            ((TextView) tarjeta.findViewById(R.id.region)).setText(CIUDADES[i].region);
            contenedor.addView(tarjeta);
            tarjetas[i] = tarjeta;
        }

        findViewById(R.id.actualizar).setOnClickListener(v -> actualizar());
    }

    @Override
    protected void onResume() {
        super.onResume();
        mostrarDiferencia();
        actualizar();
    }

    @Override
    protected void onPause() {
        super.onPause();
        principal.removeCallbacks(refrescoPeriodico);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        red.shutdownNow();
    }

    /** La diferencia cambia a lo largo del año porque cada país cambia la hora en fechas distintas. */
    private void mostrarDiferencia() {
        long ahora = System.currentTimeMillis();
        int ms = TimeZone.getTimeZone(ZONA_ESPANA).getOffset(ahora)
                - TimeZone.getTimeZone(ZONA_CHILE).getOffset(ahora);
        int minutos = Math.abs(ms) / 60_000;
        String cantidad = minutos % 60 == 0
                ? (minutos / 60) + " h"
                : String.format(Locale.ROOT, "%d h %d min", minutos / 60, minutos % 60);
        diferencia.setText(ms >= 0
                ? "España va " + cantidad + " por delante de Chile"
                : "Chile va " + cantidad + " por delante de España");
    }

    private void actualizar() {
        principal.removeCallbacks(refrescoPeriodico);
        principal.postDelayed(refrescoPeriodico, INTERVALO_MS);
        mostrarDiferencia();
        if (cargando) {
            return;
        }
        cargando = true;
        estado.setTextColor(getColor(R.color.texto_suave));
        estado.setText(R.string.cargando);
        red.execute(() -> {
            try {
                Clima.Lectura[] lecturas = Clima.descargar(CIUDADES);
                principal.post(() -> mostrar(lecturas));
            } catch (Exception e) {
                principal.post(() -> mostrarError(e));
            }
        });
    }

    private void mostrar(Clima.Lectura[] lecturas) {
        cargando = false;
        if (isDestroyed()) {
            return;
        }
        for (int i = 0; i < tarjetas.length; i++) {
            Clima.Lectura l = lecturas[i];
            View t = tarjetas[i];
            ((TextView) t.findViewById(R.id.temperatura)).setText(grados(l.temperatura));
            ((TextView) t.findViewById(R.id.cielo)).setText(Clima.describir(l.codigo, l.esDeDia));
            ((TextView) t.findViewById(R.id.detalle)).setText(
                    "Sensación " + grados(l.sensacion)
                            + "  ·  Máx " + grados(l.maxima)
                            + "  ·  Mín " + grados(l.minima));
        }
        estado.setTextColor(getColor(R.color.texto_suave));
        String hora = DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date());
        estado.setText("Actualizado a las " + hora + "  ·  Datos: Open-Meteo");
    }

    /** Si falla, se dejan a la vista los últimos datos y se avisa debajo. */
    private void mostrarError(Exception e) {
        cargando = false;
        if (isDestroyed()) {
            return;
        }
        estado.setTextColor(getColor(R.color.error));
        estado.setText("No se pudo actualizar la temperatura. Revisa la conexión y pulsa Actualizar.");
    }

    private static String grados(double valor) {
        long redondeado = Math.round(valor);
        // Evita mostrar "-0°".
        return (redondeado == 0 ? 0 : redondeado) + "°";
    }
}
