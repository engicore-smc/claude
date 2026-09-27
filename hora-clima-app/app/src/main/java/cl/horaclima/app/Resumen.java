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

    // Valores en pesos; NaN si nunca se descargaron.
    double uf = Double.NaN;
    double dolar = Double.NaN;
    double euro = Double.NaN;
    String ufFecha = "";
    String dolarFecha = "";
    String euroFecha = "";
    String monedasFuente = "";

    /** Reajuste por IPC en %, NaN si nunca se calculó. */
    double ipc = Double.NaN;
    String ipcHasta = "";
    /** Mes base con el que se calculó, p. ej. "jul 2026". */
    String ipcBase = "";

    /** Tasa hipotecaria promedio en % anual, NaN si no hay. */
    double tasa = Double.NaN;
    String tasaMes = "";
    String tasaTitulo = "";

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
            r.uf = o.optDouble("uf", Double.NaN);
            r.dolar = o.optDouble("dolar", Double.NaN);
            r.euro = o.optDouble("euro", Double.NaN);
            r.ufFecha = o.optString("ufFecha", "");
            r.dolarFecha = o.optString("dolarFecha", "");
            r.euroFecha = o.optString("euroFecha", "");
            r.monedasFuente = o.optString("monedasFuente", "");
            // "reajuste": la clave anterior ("ipc") tenía el signo contrario.
            r.ipc = o.optDouble("reajuste", Double.NaN);
            r.ipcBase = o.optString("ipcBase", "");
            r.ipcHasta = o.optString("ipcHasta", "");
            r.tasa = o.optDouble("tasa", Double.NaN);
            r.tasaMes = o.optString("tasaMes", "");
            r.tasaTitulo = o.optString("tasaTitulo", "");
        } catch (JSONException e) {
            // Datos dañados: se empieza de cero.
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
            poner(o, "uf", uf);
            poner(o, "dolar", dolar);
            poner(o, "euro", euro);
            poner(o, "reajuste", ipc);
            poner(o, "tasa", tasa);
            o.put("ufFecha", ufFecha).put("dolarFecha", dolarFecha).put("euroFecha", euroFecha)
                    .put("monedasFuente", monedasFuente).put("ipcHasta", ipcHasta).put("ipcBase", ipcBase)
                    .put("tasaMes", tasaMes).put("tasaTitulo", tasaTitulo);
            prefs(context).edit().putString(CLAVE, o.toString()).apply();
        } catch (JSONException e) {
            // No debería ocurrir; si ocurre, se conserva lo anterior.
        }
    }

    /** JSON no admite NaN: los valores que faltan simplemente no se guardan. */
    private static void poner(JSONObject o, String clave, double valor) throws JSONException {
        if (!Double.isNaN(valor)) {
            o.put(clave, valor);
        }
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
