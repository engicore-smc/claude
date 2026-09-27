package cl.horaclima.app;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.TimeZone;

/** UF, dólar, euro e IPC desde mindicador.cl (datos del Banco Central y del INE). */
final class Indicadores {

    /** Mes base del indicador de IPC. */
    static final int IPC_BASE_ANIO = 2026;
    static final int IPC_BASE_MES = 8;

    static final class Monedas {
        double uf = Double.NaN;
        double dolar = Double.NaN;
        double euro = Double.NaN;
        String ufFecha = "";
        String dolarFecha = "";
        String euroFecha = "";
        String fuente = "";
    }

    static final class Ipc {
        /** (IPC base − IPC último) / IPC base, en %. Negativo si hubo inflación. */
        double indicador;
        /** Último mes publicado que entra en el cálculo, p. ej. "sep 2026". */
        String hasta;
    }

    private Indicadores() {}

    /**
     * Primero mindicador.cl (valores oficiales, con UF). Si no responde, dólar
     * y euro de open.er-api.com; la UF queda sin dato nuevo.
     */
    static Monedas monedas(int timeoutMs) throws IOException {
        Monedas m = new Monedas();
        try {
            JSONObject todo = new JSONObject(Red.leer("https://mindicador.cl/api", timeoutMs));
            JSONObject uf = todo.optJSONObject("uf");
            JSONObject dolar = todo.optJSONObject("dolar");
            JSONObject euro = todo.optJSONObject("euro");
            if (uf != null) {
                m.uf = enRango(uf.optDouble("valor"), 10_000, 500_000);
                m.ufFecha = Formato.fechaDesdeIso(uf.optString("fecha"));
            }
            if (dolar != null) {
                m.dolar = enRango(dolar.optDouble("valor"), 100, 10_000);
                m.dolarFecha = Formato.fechaDesdeIso(dolar.optString("fecha"));
            }
            if (euro != null) {
                m.euro = enRango(euro.optDouble("valor"), 100, 10_000);
                m.euroFecha = Formato.fechaDesdeIso(euro.optString("fecha"));
            }
            m.fuente = "Banco Central de Chile";
        } catch (IOException | JSONException | RuntimeException e) {
            // Se intenta la fuente de respaldo.
        }

        if (Double.isNaN(m.dolar) || Double.isNaN(m.euro)) {
            try {
                JSONObject cuerpo = new JSONObject(
                        Red.leer("https://open.er-api.com/v6/latest/EUR", timeoutMs));
                if ("success".equals(cuerpo.optString("result"))) {
                    JSONObject tasas = cuerpo.getJSONObject("rates");
                    double clpPorEuro = tasas.getDouble("CLP");
                    double usdPorEuro = tasas.getDouble("USD");
                    if (Double.isNaN(m.euro)) {
                        m.euro = enRango(clpPorEuro, 100, 10_000);
                        m.euroFecha = "";
                    }
                    if (Double.isNaN(m.dolar)) {
                        m.dolar = enRango(clpPorEuro / usdPorEuro, 100, 10_000);
                        m.dolarFecha = "";
                    }
                    m.fuente = m.fuente.isEmpty() ? "open.er-api.com" : m.fuente + " y open.er-api.com";
                }
            } catch (IOException | JSONException | RuntimeException e) {
                // Sin respaldo: se devuelve lo que haya.
            }
        }

        if (Double.isNaN(m.uf) && Double.isNaN(m.dolar) && Double.isNaN(m.euro)) {
            throw new IOException("sin datos de monedas");
        }
        return m;
    }

    /**
     * El INE publica la variación mensual del IPC, no el índice. Se encadenan
     * las variaciones posteriores al mes base: IPC último / IPC base = Π(1 + v).
     */
    static Ipc ipc(int timeoutMs) throws IOException, JSONException {
        int anioActual = Calendar.getInstance(TimeZone.getTimeZone("America/Santiago")).get(Calendar.YEAR);
        List<int[]> meses = new ArrayList<>();       // {año, mes}
        List<Double> variaciones = new ArrayList<>();
        for (int anio = IPC_BASE_ANIO; anio <= anioActual; anio++) {
            JSONArray serie = new JSONObject(Red.leer("https://mindicador.cl/api/ipc/" + anio, timeoutMs))
                    .getJSONArray("serie");
            for (int i = 0; i < serie.length(); i++) {
                JSONObject punto = serie.getJSONObject(i);
                String fecha = punto.getString("fecha");        // "2026-09-01T03:00:00.000Z"
                int a = Integer.parseInt(fecha.substring(0, 4));
                int m = Integer.parseInt(fecha.substring(5, 7));
                if (a * 12 + m > IPC_BASE_ANIO * 12 + IPC_BASE_MES) {
                    meses.add(new int[]{a, m});
                    variaciones.add(punto.getDouble("valor"));
                }
            }
        }

        double razon = 1;
        int ultimo = IPC_BASE_ANIO * 12 + IPC_BASE_MES;
        List<Integer> vistos = new ArrayList<>();
        for (int i = 0; i < meses.size(); i++) {
            int clave = meses.get(i)[0] * 12 + meses.get(i)[1];
            if (vistos.contains(clave)) {
                continue;   // por si la API repite un mes
            }
            vistos.add(clave);
            razon *= 1 + variaciones.get(i) / 100;
            ultimo = Math.max(ultimo, clave);
        }

        Ipc ipc = new Ipc();
        ipc.indicador = (1 - razon) * 100;
        int mesUltimo = (ultimo - 1) % 12 + 1;
        int anioUltimo = (ultimo - mesUltimo) / 12;
        ipc.hasta = Formato.mes(mesUltimo, anioUltimo);
        return ipc;
    }

    private static double enRango(double valor, double min, double max) {
        return valor > min && valor < max ? valor : Double.NaN;
    }
}
