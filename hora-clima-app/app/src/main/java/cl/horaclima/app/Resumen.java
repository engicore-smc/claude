package cl.horaclima.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Últimos datos descargados, guardados en el teléfono. Los comparten la app y
 * el widget, y permiten mostrar algo aunque no haya conexión.
 */
final class Resumen {

    private static final String PREFS = "datos";
    private static final String CLAVE = "resumen";

    /** Una lectura por ciudad de {@link Ciudad#TODAS}, o null si nunca se descargó. */
    Clima.Lectura[] lecturas;
    long climaHora;

    /** Pesos por euro, o NaN si nunca se descargó. */
    double euro = Double.NaN;
    String euroFuente = "";
    String euroFecha = "";

    static synchronized Resumen cargar(Context context) {
        Resumen r = new Resumen();
        String texto = prefs(context).getString(CLAVE, null);
        if (texto == null) {
            return r;
        }
        try {
            JSONObject o = new JSONObject(texto);
            JSONArray lista = o.optJSONArray("clima");
            if (lista != null && lista.length() == Ciudad.TODAS.length) {
                r.lecturas = new Clima.Lectura[lista.length()];
                for (int i = 0; i < lista.length(); i++) {
                    r.lecturas[i] = Clima.Lectura.deJson(lista.getJSONObject(i));
                }
                r.climaHora = o.optLong("climaHora");
            }
            r.euro = o.optDouble("euro", Double.NaN);
            r.euroFuente = o.optString("euroFuente", "");
            r.euroFecha = o.optString("euroFecha", "");
        } catch (JSONException e) {
            // Datos de una versión anterior o dañados: se empieza de cero.
            return new Resumen();
        }
        return r;
    }

    synchronized void guardar(Context context) {
        try {
            JSONObject o = new JSONObject();
            if (lecturas != null) {
                JSONArray lista = new JSONArray();
                for (Clima.Lectura l : lecturas) {
                    lista.put(l.aJson());
                }
                o.put("clima", lista).put("climaHora", climaHora);
            }
            if (!Double.isNaN(euro)) {
                o.put("euro", euro).put("euroFuente", euroFuente).put("euroFecha", euroFecha);
            }
            prefs(context).edit().putString(CLAVE, o.toString()).apply();
        } catch (JSONException e) {
            // No debería ocurrir con números finitos; si ocurre, se conserva lo anterior.
        }
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
