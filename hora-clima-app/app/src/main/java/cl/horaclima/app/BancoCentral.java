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

    /**
     * Tasa de interés promedio de colocaciones para vivienda a más de 3 años,
     * en UF. Se prueban en orden; si ninguna existe en la API, se busca en el
     * catálogo y se recuerda la que se encuentre.
     */
    static final String SERIE_POR_DEFECTO = "F022.VIV.TIP.MA03.UF.Z.M";
    private static final String[] SERIES_CANDIDATAS = {SERIE_POR_DEFECTO, "F022.VIV.TIP.MA03.UF.Z.D"};

    /** La API respondió con un error propio (Codigo distinto de 0). */
    static final class ErrorApi extends IOException {
        final int codigo;

        ErrorApi(int codigo, String descripcion) {
            super("Banco Central: " + descripcion);
            this.codigo = codigo;
        }

        /** Código de serie inexistente. */
        boolean serieInvalida() {
            return codigo == -1 && getMessage().toLowerCase(Locale.ROOT).contains("series");
        }
    }

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
        if (!c.serie.isEmpty()) {
            return leerSerie(context, c, c.serie, timeoutMs);
        }

        // Sin código escrito a mano: la serie que ya funcionó, las candidatas y,
        // si ninguna existe, la que se encuentre en el catálogo.
        String detectada = prefs(context).getString("serieDetectada", "");
        if (!detectada.isEmpty()) {
            try {
                return leerSerie(context, c, detectada, timeoutMs);
            } catch (ErrorApi e) {
                if (!e.serieInvalida()) {
                    throw e;
                }
            }
        }
        for (String candidata : SERIES_CANDIDATAS) {
            try {
                Tasa t = leerSerie(context, c, candidata, timeoutMs);
                prefs(context).edit().putString("serieDetectada", candidata).apply();
                return t;
            } catch (ErrorApi e) {
                if (!e.serieInvalida()) {
                    throw e;
                }
            }
        }
        String encontrada = buscarSerie(c, timeoutMs);
        Tasa t = leerSerie(context, c, encontrada, timeoutMs);
        prefs(context).edit().putString("serieDetectada", encontrada).apply();
        return t;
    }

    private static Tasa leerSerie(Context context, Cuenta c, String codigo, int timeoutMs)
            throws IOException, JSONException {
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
        boolean mensual = codigo.endsWith(".M");
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
            // Serie mensual: "jul 2026"; diaria o semanal: la fecha completa.
            t.mes = mensual && p.length == 3
                    ? Formato.mes(Integer.parseInt(p[1]), Integer.parseInt(p[2])) : fecha;
            t.titulo = serie.optString("descripEsp", "") + " (" + codigo + ")";
            if (!t.titulo.equals(c.titulo)) {
                prefs(context).edit().putString("titulo", t.titulo).apply();
            }
            return t;
        }
        throw new IOException("la serie " + codigo + " no tiene datos recientes");
    }

    /**
     * Busca en el catálogo (mensual y luego diario) la tasa de colocaciones
     * para vivienda en UF. Se prefiere la de más de 3 años y la promedio.
     */
    private static String buscarSerie(Cuenta c, int timeoutMs) throws IOException, JSONException {
        String mejor = null;
        int mejorPuntos = 0;
        for (String frecuencia : new String[]{"MONTHLY", "DAILY"}) {
            JSONArray series = consultar(c, "SearchSeries", "&frequency=" + frecuencia, timeoutMs)
                    .getJSONArray("SeriesInfos");
            for (int i = 0; i < series.length(); i++) {
                JSONObject info = series.getJSONObject(i);
                String id = info.optString("seriesId", "");
                String t = info.optString("spanishTitle", "").toLowerCase(Locale.ROOT);
                if (!t.contains("vivienda") || !(t.contains("tasa") || t.contains("interés"))) {
                    continue;
                }
                int puntos = 10;
                if (t.contains("uf") || t.contains("reajustable")) puntos += 5;
                if (t.contains("3 años") || id.contains("MA03")) puntos += 3;
                if (t.contains("promedio") || id.contains(".TIP.")) puntos += 2;
                if (frecuencia.equals("MONTHLY")) puntos += 1;
                if (t.contains("monto") || t.contains("número") || t.contains("stock")
                        || t.contains("spread") || t.contains("diferencial")) puntos -= 20;
                if (puntos > mejorPuntos) {
                    mejorPuntos = puntos;
                    mejor = id;
                }
            }
            if (mejorPuntos >= 18) {
                break;      // ya hay una buena candidata mensual
            }
        }
        if (mejor == null || mejor.isEmpty()) {
            throw new IOException("no se encontró la serie de tasa hipotecaria en el catálogo");
        }
        return mejor;
    }

    private static JSONObject consultar(Cuenta c, String funcion, String extra, int timeoutMs)
            throws IOException, JSONException {
        String url = API + "?token=" + codificar(c.token) + "&function=" + funcion + extra;
        JSONObject cuerpo = new JSONObject(Red.leer(url, timeoutMs));
        int codigo = cuerpo.optInt("Codigo", -99);
        if (codigo != 0) {
            // Por ejemplo, token inválido o vencido, o serie inexistente.
            throw new ErrorApi(codigo, cuerpo.optString("Descripcion", "error"));
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
