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
import java.util.Locale;

/**
 * Widget de la pantalla de inicio: hora y minuto de Chile y España (los
 * TextClock avanzan solos) y un resumen de temperaturas y euro.
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

        vista.setTextViewText(R.id.w_euro, Double.isNaN(r.euro)
                ? "1 € = —"
                : "1 € = $" + pesos(r.euro, 0));
        vista.setTextViewText(R.id.w_actualizado, r.climaHora > 0
                ? "act. " + DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(r.climaHora))
                : "");

        Intent abrir = new Intent(context, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        vista.setOnClickPendingIntent(R.id.w_raiz, PendingIntent.getActivity(
                context, 0, abrir, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));

        manager.updateAppWidget(ids, vista);
    }

    /** Pesos chilenos con punto de miles: 1.085 o 1.085,32. */
    static String pesos(double valor, int decimales) {
        // A mano y no con el Locale: los datos del español omiten el punto en
        // números de cuatro cifras ("1085"), y aquí se quiere siempre "1.085".
        String ingles = String.format(Locale.ROOT, "%,." + decimales + "f", valor);
        StringBuilder chileno = new StringBuilder(ingles.length());
        for (char c : ingles.toCharArray()) {
            chileno.append(c == ',' ? '.' : c == '.' ? ',' : c);
        }
        return chileno.toString();
    }
}
