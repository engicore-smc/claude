package cl.horaclima.app;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;

/** Precio del euro en pesos chilenos. */
final class Euro {

    static final class Cotizacion {
        /** Pesos chilenos por 1 euro. */
        double valor;
        String fuente;
        /** Fecha del valor (dd-mm-aaaa), o vacía si la fuente no la da. */
        String fecha;
    }

    private Euro() {}

    /**
     * Primero el valor oficial del Banco Central de Chile (vía mindicador.cl);
     * si no responde, el tipo de cambio de open.er-api.com. Ambos gratis y sin clave.
     */
    static Cotizacion descargar(int timeoutMs) throws IOException, JSONException {
        try {
            return desdeMindicador(timeoutMs);
        } catch (IOException | JSONException | RuntimeException e) {
            return desdeErApi(timeoutMs);
        }
    }

    private static Cotizacion desdeMindicador(int timeoutMs) throws IOException, JSONException {
        JSONObject cuerpo = new JSONObject(Red.leer("https://mindicador.cl/api/euro", timeoutMs));
        // "serie" viene ordenada del día más reciente al más antiguo.
        JSONObject ultimo = cuerpo.getJSONArray("serie").getJSONObject(0);
        Cotizacion c = new Cotizacion();
        c.valor = validar(ultimo.getDouble("valor"));
        c.fuente = "Banco Central de Chile";
        c.fecha = fechaDesdeIso(ultimo.optString("fecha", ""));
        return c;
    }

    private static Cotizacion desdeErApi(int timeoutMs) throws IOException, JSONException {
        JSONObject cuerpo = new JSONObject(Red.leer("https://open.er-api.com/v6/latest/EUR", timeoutMs));
        if (!"success".equals(cuerpo.optString("result"))) {
            throw new IOException("open.er-api.com no devolvió datos");
        }
        Cotizacion c = new Cotizacion();
        c.valor = validar(cuerpo.getJSONObject("rates").getDouble("CLP"));
        c.fuente = "open.er-api.com";
        c.fecha = "";
        return c;
    }

    /** Descarta respuestas absurdas en vez de mostrarlas. */
    private static double validar(double valor) throws IOException {
        if (!(valor > 100 && valor < 100_000)) {
            throw new IOException("valor del euro fuera de rango: " + valor);
        }
        return valor;
    }

    /** "2026-09-26T03:00:00.000Z" → "26-09-2026". */
    private static String fechaDesdeIso(String iso) {
        if (iso.length() < 10) {
            return "";
        }
        String[] p = iso.substring(0, 10).split("-");
        return p.length == 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
    }
}
