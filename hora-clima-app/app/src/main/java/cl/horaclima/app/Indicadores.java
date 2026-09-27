package cl.horaclima.app;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;

/** UF, dólar y euro desde mindicador.cl (datos del Banco Central); el IPC se deduce de la UF. */
final class Indicadores {

    /** Mes base del indicador de IPC. */
    static final int IPC_BASE_ANIO = 2026;
    static final int IPC_BASE_MES = 7;

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
     * El cociente IPC último / IPC base se obtiene de la UF, que por ley sube
     * cada día según el IPC: del día 10 del mes t al 9 del mes t+1 crece en
     * forma geométrica exactamente el IPC del mes t−1. Así:
     * <ul>
     *   <li>UF(9 del mes t+1) / UF(9 del mes t) = 1 + IPC(t−1), y los períodos
     *       completos se encadenan solos: IPC(m) / IPC(base) = UF(9 de m+2) / UF(9 de base+2).</li>
     *   <li>En el período en curso, que empieza el día 9 (S) y dura D días, con
     *       k días transcurridos hasta hoy (T): 1 + IPC = (UF(T) / UF(S))^(D/k).</li>
     * </ul>
     * No depende de que alguien cargue la serie del IPC: basta la UF, que el
     * Banco Central publica a diario.
     */
    static Ipc ipc(int timeoutMs) throws IOException, JSONException {
        JSONObject hoy = new JSONObject(Red.leer("https://mindicador.cl/api/uf", timeoutMs))
                .getJSONArray("serie").getJSONObject(0);
        LocalDate t = LocalDate.parse(hoy.getString("fecha").substring(0, 10));
        double ufT = hoy.getDouble("valor");

        // Inicio del período en curso: el día 9 más reciente estrictamente anterior a T.
        LocalDate s = t.getDayOfMonth() >= 10 ? t.withDayOfMonth(9) : t.minusMonths(1).withDayOfMonth(9);
        // El período que empieza el 9 del mes m aplica el IPC del mes m−1.
        YearMonth mesIpc = YearMonth.from(s).minusMonths(1);
        YearMonth base = YearMonth.of(IPC_BASE_ANIO, IPC_BASE_MES);
        // Primer día 9 cuyo período aplica un IPC posterior al base.
        LocalDate ancla = base.plusMonths(2).atDay(9);

        Ipc ipc = new Ipc();
        if (!mesIpc.isAfter(base)) {
            ipc.indicador = 0;
            ipc.hasta = Formato.mes(base.getMonthValue(), base.getYear());
            return ipc;
        }

        double ufS = ufDelDia(s, timeoutMs);
        double completos = s.equals(ancla) ? 1 : ufS / ufDelDia(ancla, timeoutMs);
        long d = ChronoUnit.DAYS.between(s, s.plusMonths(1));
        long k = ChronoUnit.DAYS.between(s, t);
        double enCurso = Math.pow(ufT / ufS, (double) d / k);
        double razon = completos * enCurso;
        if (!(razon > 0.5 && razon < 2)) {
            throw new IOException("cálculo del IPC fuera de rango: " + razon);
        }

        ipc.indicador = (1 - razon) * 100;
        ipc.hasta = Formato.mes(mesIpc.getMonthValue(), mesIpc.getYear());
        return ipc;
    }

    private static double ufDelDia(LocalDate dia, int timeoutMs) throws IOException, JSONException {
        String fecha = String.format(java.util.Locale.ROOT, "%02d-%02d-%04d",
                dia.getDayOfMonth(), dia.getMonthValue(), dia.getYear());
        JSONArray serie = new JSONObject(Red.leer("https://mindicador.cl/api/uf/" + fecha, timeoutMs))
                .getJSONArray("serie");
        if (serie.length() == 0) {
            throw new IOException("sin UF para el " + fecha);
        }
        return serie.getJSONObject(0).getDouble("valor");
    }

    private static double enRango(double valor, double min, double max) {
        return valor > min && valor < max ? valor : Double.NaN;
    }
}
