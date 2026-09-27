package cl.horaclima.app;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Descarga de texto por HTTP. Se llama siempre fuera del hilo principal. */
final class Red {

    private Red() {}

    static String leer(String direccion, int timeoutMs) throws IOException {
        HttpURLConnection conexion = (HttpURLConnection) new URL(direccion).openConnection();
        conexion.setConnectTimeout(timeoutMs);
        conexion.setReadTimeout(timeoutMs);
        conexion.setRequestProperty("Accept", "application/json");
        try {
            int codigo = conexion.getResponseCode();
            if (codigo != HttpURLConnection.HTTP_OK) {
                throw new IOException(direccion + " respondió " + codigo);
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
}
