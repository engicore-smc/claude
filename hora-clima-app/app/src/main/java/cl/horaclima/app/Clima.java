package cl.horaclima.app;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Temperatura actual desde Open-Meteo (gratis, sin clave). */
final class Clima {

    /** Lo que se muestra de una ciudad. */
    static final class Lectura {
        double temperatura;
        double sensacion;
        double maxima;
        double minima;
        int codigo;
        boolean esDeDia;
    }

    private Clima() {}

    /** Pide todas las ciudades en una sola consulta. Se llama fuera del hilo principal. */
    static Lectura[] descargar(Ciudad[] ciudades) throws IOException, org.json.JSONException {
        StringBuilder lat = new StringBuilder();
        StringBuilder lon = new StringBuilder();
        for (int i = 0; i < ciudades.length; i++) {
            if (i > 0) {
                lat.append(',');
                lon.append(',');
            }
            lat.append(String.format(Locale.ROOT, "%.4f", ciudades[i].latitud));
            lon.append(String.format(Locale.ROOT, "%.4f", ciudades[i].longitud));
        }
        String url = "https://api.open-meteo.com/v1/forecast"
                + "?latitude=" + lat
                + "&longitude=" + lon
                + "&current=temperature_2m,apparent_temperature,weather_code,is_day"
                + "&daily=temperature_2m_max,temperature_2m_min"
                + "&timezone=auto&forecast_days=1";

        String cuerpo = leer(url);
        // Con varias ciudades la respuesta es una lista; con una sola, un objeto.
        JSONArray lista = cuerpo.trim().startsWith("[")
                ? new JSONArray(cuerpo)
                : new JSONArray().put(new JSONObject(cuerpo));

        Lectura[] lecturas = new Lectura[ciudades.length];
        for (int i = 0; i < ciudades.length; i++) {
            JSONObject lugar = lista.getJSONObject(i);
            JSONObject actual = lugar.getJSONObject("current");
            JSONObject diario = lugar.getJSONObject("daily");
            Lectura l = new Lectura();
            l.temperatura = actual.getDouble("temperature_2m");
            l.sensacion = actual.getDouble("apparent_temperature");
            l.codigo = actual.getInt("weather_code");
            l.esDeDia = actual.optInt("is_day", 1) == 1;
            l.maxima = diario.getJSONArray("temperature_2m_max").getDouble(0);
            l.minima = diario.getJSONArray("temperature_2m_min").getDouble(0);
            lecturas[i] = l;
        }
        return lecturas;
    }

    private static String leer(String direccion) throws IOException {
        HttpURLConnection conexion = (HttpURLConnection) new URL(direccion).openConnection();
        conexion.setConnectTimeout(15_000);
        conexion.setReadTimeout(15_000);
        try {
            int codigo = conexion.getResponseCode();
            if (codigo != HttpURLConnection.HTTP_OK) {
                throw new IOException("el servidor respondió " + codigo);
            }
            try (InputStream entrada = conexion.getInputStream()) {
                ByteArrayOutputStream salida = new ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int n;
                while ((n = entrada.read(buffer)) != -1) {
                    salida.write(buffer, 0, n);
                }
                return salida.toString(StandardCharsets.UTF_8.name());
            }
        } finally {
            conexion.disconnect();
        }
    }

    /** Texto e icono del código de tiempo WMO que usa Open-Meteo. */
    static String describir(int codigo, boolean esDeDia) {
        switch (codigo) {
            case 0: return esDeDia ? "☀️ Despejado" : "🌙 Despejado";
            case 1: return esDeDia ? "🌤️ Mayormente despejado" : "🌙 Mayormente despejado";
            case 2: return "⛅ Parcialmente nublado";
            case 3: return "☁️ Nublado";
            case 45: case 48: return "🌫️ Niebla";
            case 51: case 53: case 55: return "🌦️ Llovizna";
            case 56: case 57: return "🌧️ Llovizna helada";
            case 61: return "🌧️ Lluvia débil";
            case 63: return "🌧️ Lluvia";
            case 65: return "🌧️ Lluvia fuerte";
            case 66: case 67: return "🌧️ Lluvia helada";
            case 71: return "🌨️ Nieve débil";
            case 73: return "🌨️ Nieve";
            case 75: return "❄️ Nieve fuerte";
            case 77: return "🌨️ Granizo fino";
            case 80: case 81: return "🌦️ Chubascos";
            case 82: return "⛈️ Chubascos fuertes";
            case 85: case 86: return "🌨️ Chubascos de nieve";
            case 95: return "⛈️ Tormenta";
            case 96: case 99: return "⛈️ Tormenta con granizo";
            default: return "";
        }
    }
}
