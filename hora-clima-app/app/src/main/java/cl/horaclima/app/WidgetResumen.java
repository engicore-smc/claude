package cl.horaclima.app;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import java.text.DateFormat;
import java.util.Date;

/**
 * Widget de la pantalla de inicio: hora y minuto de Chile y España (los
 * TextClock avanzan solos), temperaturas e indicadores (UF, dólar, euro,
 * IPC y tasa hipotecaria).
 * Android lo despierta cada 30 minutos para descargar datos nuevos; al
 * tocarlo se abre la app, que también lo actualiza.
 */
public class WidgetResumen extends AppWidgetProvider {

    private static final int[] TEMPERATURAS = {R.id.w_temp0, R.id.w_temp1, R.id.w_temp2};
    private static final int[] NOMBRES = {R.id.w_nombre0, R.id.w_nombre1, R.id.w_nombre2};

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        // Primero lo guardado, para que nunca quede vacío; luego se descarga.
        pintar(context);
        PendingResult pendiente = goAsync();
        new Thread(() -> {
            try {
                Actualizador.actualizar(context, 8_000);
            } finally {
                pendiente.finish();
            }
        }).start();
    }

    /** Redibuja todos los widgets con los datos guardados. */
    static void pintar(Context context) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        int[] ids = manager.getAppWidgetIds(new ComponentName(context, WidgetResumen.class));
        if (ids.length == 0) {
            return;
        }
        Resumen r = Resumen.cargar(context);
        RemoteViews vista = new RemoteViews(context.getPackageName(), R.layout.widget_resumen);

        for (int i = 0; i < Ciudad.TODAS.length; i++) {
            vista.setTextViewText(NOMBRES[i], Ciudad.TODAS[i].nombre);
            String texto = "—";
            if (r.lecturas != null) {
                Clima.Lectura l = r.lecturas[i];
                texto = Clima.grados(l.temperatura) + " " + Clima.icono(l.codigo, l.esDeDia);
            }
            vista.setTextViewText(TEMPERATURAS[i], texto);
        }

        vista.setTextViewText(R.id.w_uf, pesos(r.uf));
        vista.setTextViewText(R.id.w_dolar, pesos(r.dolar));
        vista.setTextViewText(R.id.w_euro, pesos(r.euro));
        vista.setTextViewText(R.id.w_ipc, Double.isNaN(r.ipc) ? "—" : Formato.porcentajeConSigno(r.ipc, 1));
        vista.setTextViewText(R.id.w_tasa, Double.isNaN(r.tasa) ? "—" : Formato.numero(r.tasa, 2) + "%");
        vista.setTextViewText(R.id.w_actualizado, r.climaHora > 0
                ? DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(r.climaHora))
                : "");

        Intent abrir = new Intent(context, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        vista.setOnClickPendingIntent(R.id.w_raiz, PendingIntent.getActivity(
                context, 0, abrir, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));

        manager.updateAppWidget(ids, vista);
    }

    /** Pesos sin decimales, para que quepan: "1.085". */
    private static String pesos(double valor) {
        return Double.isNaN(valor) ? "—" : Formato.numero(valor, 0);
    }
}
