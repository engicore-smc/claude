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
 * API del Banco Central (BDE). Pide usuario y contraseña gratuitos, que se
 * escriben en la app y quedan solo en el teléfono.
 */
final class BancoCentral {

    private static final String PREFS = "bcentral";
    private static final String API = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx";

    static final class Tasa {
        /** % anual. */
        double valor;
        /** Mes del dato, p. ej. "jul 2026". */
        String mes;
        /** Nombre de la serie según el Banco Central, para saber qué se muestra. */
        String titulo;
    }

    static final class Cuenta {
        String usuario = "";
        String clave = "";
        /** Código de la serie; vacío = buscarla automáticamente. */
        String serie = "";
        String titulo = "";

        boolean configurada() {
            return !usuario.isEmpty() && !clave.isEmpty();
        }
    }

    private BancoCentral() {}

    static Cuenta cuenta(Context context) {
        SharedPreferences p = prefs(context);
        Cuenta c = new Cuenta();
        c.usuario = p.getString("usuario", "");
        c.clave = p.getString("clave", "");
        c.serie = p.getString("serie", "");
        c.titulo = p.getString("titulo", "");
        return c;
    }

    static void guardarCuenta(Context context, String usuario, String clave, String serie) {
        Cuenta anterior = cuenta(context);
        SharedPreferences.Editor e = prefs(context).edit()
                .putString("usuario", usuario.trim())
                .putString("clave", clave)
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
        if (c.serie.isEmpty()) {
            buscarSerie(context, c, timeoutMs);
        }

        Calendar hasta = Calendar.getInstance();
        Calendar desde = (Calendar) hasta.clone();
        desde.add(Calendar.MONTH, -12);
        SimpleDateFormat iso = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
        JSONObject cuerpo = consultar(c, "GetSeries",
                "&timeseries=" + codificar(c.serie)
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
            String titulo = serie.optString("descripEsp", "");
            t.titulo = titulo.isEmpty() ? c.titulo : titulo;
            return t;
        }
        throw new IOException("la serie " + c.serie + " no tiene datos recientes");
    }

    /**
     * Busca entre las series mensuales la de tasa de interés de créditos para
     * vivienda en UF, y la recuerda. Se puede cambiar a mano en los ajustes.
     */
    private static void buscarSerie(Context context, Cuenta c, int timeoutMs)
            throws IOException, JSONException {
        JSONObject cuerpo = consultar(c, "SearchSeries", "&frequency=MONTHLY", timeoutMs);
        JSONArray series = cuerpo.getJSONArray("SeriesInfos");
        String mejor = null;
        String mejorTitulo = null;
        int mejorPuntos = 0;
        for (int i = 0; i < series.length(); i++) {
            JSONObject s = series.getJSONObject(i);
            String titulo = s.optString("spanishTitle", "");
            String t = titulo.toLowerCase(Locale.ROOT);
            if (!t.contains("vivienda") || !(t.contains("tasa") || t.contains("interés"))) {
                continue;
            }
            int puntos = 5;
            if (t.contains("uf") || t.contains("reajustable")) puntos += 3;
            if (t.contains("promedio")) puntos += 2;
            if (t.contains("colocaciones") || t.contains("créditos") || t.contains("hipotecari")) puntos += 1;
            if (t.contains("monto") || t.contains("número") || t.contains("stock")
                    || t.contains("spread") || t.contains("diferencial")) puntos -= 10;
            if (puntos > mejorPuntos) {
                mejorPuntos = puntos;
                mejor = s.optString("seriesId");
                mejorTitulo = titulo;
            }
        }
        if (mejor == null || mejor.isEmpty()) {
            throw new IOException("no se encontró la serie de tasa hipotecaria");
        }
        c.serie = mejor;
        c.titulo = mejorTitulo;
        prefs(context).edit().putString("serie", mejor).putString("titulo", mejorTitulo).apply();
    }

    private static JSONObject consultar(Cuenta c, String funcion, String extra, int timeoutMs)
            throws IOException, JSONException {
        String url = API + "?user=" + codificar(c.usuario) + "&pass=" + codificar(c.clave)
                + "&function=" + funcion + extra;
        JSONObject cuerpo = new JSONObject(Red.leer(url, timeoutMs));
        if (cuerpo.optInt("Codigo", -1) != 0) {
            // Por ejemplo, usuario o contraseña incorrectos.
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
