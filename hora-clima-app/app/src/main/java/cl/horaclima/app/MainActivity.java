package cl.horaclima.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Insets;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.text.DateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Pantalla única: la hora en Chile y España (la dan los TextClock del layout,
 * con la zona horaria del teléfono), la temperatura de tres ciudades e
 * indicadores económicos de Chile.
 */
public class MainActivity extends Activity {

    private static final Ciudad[] CIUDADES = Ciudad.TODAS;

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
    // Filas de la tarjeta de indicadores.
    private View filaUf;
    private View filaDolar;
    private View filaEuro;
    private View filaIpc;
    private View filaTasa;
    /** Último error del Banco Central, para mostrarlo en su fila. */
    private String errorTasa = "";
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

        ViewGroup indicadores = findViewById(R.id.indicadores);
        filaUf = fila(inflater, indicadores, "UF");
        filaDolar = fila(inflater, indicadores, "Dólar observado");
        filaEuro = fila(inflater, indicadores, "Euro");
        filaIpc = fila(inflater, indicadores, "Indicador IPC");
        filaTasa = fila(inflater, indicadores, "Tasa hipotecaria");
        filaTasa.setOnClickListener(v -> configurarBancoCentral());

        findViewById(R.id.actualizar).setOnClickListener(v -> actualizar());

        // Lo último guardado, mientras llegan los datos nuevos.
        mostrar(Resumen.cargar(this));
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
            Actualizador.Resultado resultado = Actualizador.actualizar(this, 15_000);
            Resumen resumen = Resumen.cargar(this);
            principal.post(() -> terminar(resultado, resumen));
        });
    }

    private void terminar(Actualizador.Resultado resultado, Resumen resumen) {
        cargando = false;
        if (isDestroyed()) {
            return;
        }
        errorTasa = resultado.tasaError;
        mostrar(resumen);
        if (resultado.todoOk()) {
            return;
        }
        // Lo que falló se avisa debajo; a la vista quedan los últimos datos.
        StringBuilder que = new StringBuilder();
        if (!resultado.climaOk) que.append(", temperatura");
        if (!resultado.monedasOk) que.append(", UF/dólar/euro");
        if (!resultado.ipcOk) que.append(", IPC");
        if (!resultado.tasaOk && !resultado.tasaSinCuenta) que.append(", tasa hipotecaria");
        estado.setTextColor(getColor(R.color.error));
        estado.setText("No se pudo actualizar: " + que.substring(2)
                + ". Se muestran los últimos datos; pulsa Actualizar para reintentar.");
    }

    private void mostrar(Resumen r) {
        if (r.lecturas != null) {
            for (int i = 0; i < tarjetas.length; i++) {
                Clima.Lectura l = r.lecturas[i];
                View t = tarjetas[i];
                ((TextView) t.findViewById(R.id.temperatura)).setText(Clima.grados(l.temperatura));
                ((TextView) t.findViewById(R.id.cielo)).setText(Clima.describir(l.codigo, l.esDeDia));
                ((TextView) t.findViewById(R.id.detalle)).setText(
                        "Sensación " + Clima.grados(l.sensacion)
                                + "  ·  Máx " + Clima.grados(l.maxima)
                                + "  ·  Mín " + Clima.grados(l.minima));
            }
        }
        poner(filaUf, pesos(r.uf, 2), r.ufFecha);
        poner(filaDolar, pesos(r.dolar, 2), unir(r.dolarFecha, r.monedasFuente));
        poner(filaEuro, pesos(r.euro, 2), r.euroFecha);

        String base = Formato.mes(Indicadores.IPC_BASE_MES, Indicadores.IPC_BASE_ANIO);
        if (Double.isNaN(r.ipc)) {
            poner(filaIpc, "—", "(IPC " + base + " − IPC último) / IPC " + base);
        } else if (r.ipcHasta.equals(base)) {
            poner(filaIpc, Formato.porcentajeConSigno(r.ipc, 2),
                    "Aún no se publica un IPC posterior a " + base);
        } else {
            poner(filaIpc, Formato.porcentajeConSigno(r.ipc, 2),
                    "(IPC " + base + " − IPC " + r.ipcHasta + ") / IPC " + base);
        }

        if (!BancoCentral.cuenta(this).configurada()) {
            poner(filaTasa, "—", "Toca para configurar tu cuenta del Banco Central");
        } else if (!errorTasa.isEmpty()) {
            poner(filaTasa, Double.isNaN(r.tasa) ? "—" : Formato.numero(r.tasa, 2) + " %",
                    errorTasa + " · toca para revisar la cuenta");
        } else {
            poner(filaTasa, Double.isNaN(r.tasa) ? "—" : Formato.numero(r.tasa, 2) + " %",
                    unir("Promedio bancos en Chile, UF", r.tasaMes));
        }

        estado.setTextColor(getColor(R.color.texto_suave));
        if (r.climaHora > 0) {
            String hora = DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(r.climaHora));
            estado.setText("Actualizado a las " + hora + "  ·  Clima: Open-Meteo  ·  Indicadores: mindicador.cl y Banco Central");
        } else {
            estado.setText("");
        }
    }

    private static View fila(LayoutInflater inflater, ViewGroup padre, String nombre) {
        View fila = inflater.inflate(R.layout.item_indicador, padre, false);
        ((TextView) fila.findViewById(R.id.ind_nombre)).setText(nombre);
        padre.addView(fila);
        return fila;
    }

    private static void poner(View fila, String valor, String detalle) {
        ((TextView) fila.findViewById(R.id.ind_valor)).setText(valor);
        TextView d = fila.findViewById(R.id.ind_detalle);
        d.setText(detalle);
        d.setVisibility(detalle.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private static String pesos(double valor, int decimales) {
        return Double.isNaN(valor) ? "—" : "$" + Formato.numero(valor, decimales);
    }

    private static String unir(String a, String b) {
        return a.isEmpty() ? b : b.isEmpty() ? a : a + " · " + b;
    }

    /** Usuario y contraseña de la API del Banco Central; se guardan solo en el teléfono. */
    private void configurarBancoCentral() {
        BancoCentral.Cuenta c = BancoCentral.cuenta(this);
        int margen = Math.round(20 * getResources().getDisplayMetrics().density);
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(margen, margen / 2, margen, 0);

        TextView ayuda = new TextView(this);
        ayuda.setText("Crea una cuenta gratuita en la API del Banco Central "
                + "(si3.bcentral.cl → Web Services), actívala desde el correo y escribe "
                + "aquí el usuario y la contraseña de la API. Solo se guardan en este teléfono."
                + (c.titulo.isEmpty() ? "" : "\n\nSerie actual: " + c.titulo));
        ayuda.setTextColor(getColor(R.color.texto_suave));
        form.addView(ayuda);

        EditText usuario = campo(form, "Usuario (correo)", c.usuario,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        EditText clave = campo(form, "Contraseña", c.clave,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText serie = campo(form, "Código de serie (vacío = " + BancoCentral.SERIE_POR_DEFECTO + ")", c.serie,
                InputType.TYPE_CLASS_TEXT);

        new AlertDialog.Builder(this)
                .setTitle("Cuenta del Banco Central")
                .setView(form)
                .setPositiveButton("Guardar", (d, w) -> {
                    BancoCentral.guardarCuenta(this, usuario.getText().toString(),
                            clave.getText().toString(), serie.getText().toString());
                    errorTasa = "";
                    actualizar();
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private EditText campo(LinearLayout form, String pista, String valor, int tipo) {
        EditText e = new EditText(this);
        e.setHint(pista);
        e.setText(valor);
        e.setInputType(tipo);
        e.setSingleLine(true);
        form.addView(e);
        return e;
    }
}
