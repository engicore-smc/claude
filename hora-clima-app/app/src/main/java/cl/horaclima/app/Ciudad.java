package cl.horaclima.app;

/** Un lugar del que se muestra la temperatura. */
final class Ciudad {
    final String nombre;
    final String region;
    final double latitud;
    final double longitud;

    Ciudad(String nombre, String region, double latitud, double longitud) {
        this.nombre = nombre;
        this.region = region;
        this.latitud = latitud;
        this.longitud = longitud;
    }
}
