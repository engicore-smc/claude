package cl.horaclima.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

/**
 * Tasa promedio de los créditos hipotecarios del sistema bancario, desde la
 * API del Banco Central (BDE). Se autentica con el "API Key Token" de la
 * cuenta (Mi Cuenta → Apikey Token), que se pega en la app y queda solo en el
 * teléfono. El sistema antiguo de usuario y contraseña ya no se acepta.
 */
final class BancoCentral {

    private static final String PREFS = "bcentral";
    private static final String API = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx";

    /** Tasa de interés promedio de colocaciones para vivienda a más de 3 años, en UF, mensual. */
    static final String SERIE_POR_DEFECTO = "F022.VIV.TIP.MA03.UF.Z.M";

    static final class Tasa {
        /** % anual. */
        double valor;
        /** Mes del dato, p. ej. "jul 2026". */
        String mes;
        /** Nombre de la serie según el Banco Central, para saber qué se muestra. */
        String titulo;
    }

    static final class Cuenta {
        String token = "";
        /** Código de la serie; vacío = {@link #SERIE_POR_DEFECTO}. */
        String serie = "";
        String titulo = "";

        boolean configurada() {
            return !token.isEmpty();
        }
    }

    private BancoCentral() {}

    static Cuenta cuenta(Context context) {
        SharedPreferences p = prefs(context);
        Cuenta c = new Cuenta();
        c.token = p.getString("token", "");
        c.serie = p.getString("serie", "");
        c.titulo = p.getString("titulo", "");
        return c;
    }

    static void guardarCuenta(Context context, String token, String serie) {
        Cuenta anterior = cuenta(context);
        SharedPreferences.Editor e = prefs(context).edit()
                .putString("token", token.trim())
                .remove("usuario")      // del sistema antiguo
                .remove("clave")
                .putString("serie", serie.trim());
        if (!serie.trim().equals(anterior.serie)) {
            e.putString("titulo", "");
        }
        e.apply();
    }

    /** null si la cuenta no está configurada. */
    static Tasa hipotecaria(Context context, int timeoutMs) throws IOException, JSONException {
        Cuenta c = cuenta(context);
        if (!c.configurada()) {
            return null;
        }
        String codigo = c.serie.isEmpty() ? SERIE_POR_DEFECTO : c.serie;

        Calendar hasta = Calendar.getInstance();
        Calendar desde = (Calendar) hasta.clone();
        desde.add(Calendar.MONTH, -12);
        SimpleDateFormat iso = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        JSONObject cuerpo = consultar(c, "GetSeries",
                "&timeseries=" + codificar(codigo)
                        + "&firstdate=" + iso.format(desde.getTime())
                        + "&lastdate=" + iso.format(hasta.getTime()),
                timeoutMs);

        JSONObject serie = cuerpo.getJSONObject("Series");
        JSONArray obs = serie.getJSONArray("Obs");
        for (int i = obs.length() - 1; i >= 0; i--) {
            JSONObject o = obs.getJSONObject(i);
            double valor;
            try {
                valor = Double.parseDouble(o.optString("value").replace(',', '.'));
            } catch (NumberFormatException e) {
                continue;
            }
            if (Double.isNaN(valor) || !"OK".equalsIgnoreCase(o.optString("statusCode", "OK"))) {
                continue;
            }
            Tasa t = new Tasa();
            t.valor = valor;
            String fecha = o.optString("indexDateString");     // "01-07-2026"
            String[] p = fecha.split("-");
            t.mes = p.length == 3 ? Formato.mes(Integer.parseInt(p[1]), Integer.parseInt(p[2])) : fecha;
            t.titulo = serie.optString("descripEsp", "");
            if (!t.titulo.equals(c.titulo)) {
                prefs(context).edit().putString("titulo", t.titulo).apply();
            }
            return t;
        }
        throw new IOException("la serie " + codigo + " no tiene datos recientes");
    }

    private static JSONObject consultar(Cuenta c, String funcion, String extra, int timeoutMs)
            throws IOException, JSONException {
        String url = API + "?token=" + codificar(c.token) + "&function=" + funcion + extra;
        JSONObject cuerpo = new JSONObject(Red.leer(url, timeoutMs));
        if (cuerpo.optInt("Codigo", -1) != 0) {
            // Por ejemplo, token inválido o vencido.
            throw new IOException("Banco Central: " + cuerpo.optString("Descripcion", "error"));
        }
        return cuerpo;
    }

    private static String codificar(String texto) {
        try {
            return URLEncoder.encode(texto, "UTF-8");
        } catch (java.io.UnsupportedEncodingException e) {
            throw new IllegalStateException(e);   // UTF-8 existe siempre
        }
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
