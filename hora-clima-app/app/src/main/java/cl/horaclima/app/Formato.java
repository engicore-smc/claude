package cl.horaclima.app;

import java.util.Locale;

/** Números al estilo chileno: punto de miles y coma decimal. */
final class Formato {

    private static final String[] MESES = {
            "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"};

    private Formato() {}

    /**
     * 1085.32 → "1.085,32". A mano y no con el Locale: los datos del español
     * omiten el punto en números de cuatro cifras ("1085").
     */
    static String numero(double valor, int decimales) {
        String ingles = String.format(Locale.ROOT, "%,." + decimales + "f", valor);
        StringBuilder chileno = new StringBuilder(ingles.length());
        for (char c : ingles.toCharArray()) {
            chileno.append(c == ',' ? '.' : c == '.' ? ',' : c);
        }
        return chileno.toString();
    }

    /** Porcentaje con signo explícito: "+0,25 %", "−1,20 %". */
    static String porcentajeConSigno(double valor, int decimales) {
        String texto = numero(Math.abs(valor), decimales);
        if (Math.abs(valor) < Math.pow(10, -decimales) / 2) {
            return texto + " %";
        }
        return (valor > 0 ? "+" : "−") + texto + " %";
    }

    /** 8, 2026 → "ago 2026". */
    static String mes(int mes, int anio) {
        return MESES[mes - 1] + " " + anio;
    }

    /** "2026-09-26T03:00:00.000Z" → "26-09-2026". */
    static String fechaDesdeIso(String iso) {
        if (iso == null || iso.length() < 10) {
            return "";
        }
        String[] p = iso.substring(0, 10).split("-");
        return p.length == 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
    }
}
