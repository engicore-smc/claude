package cl.horaclima.app;

/** Un lugar del que se muestra la temperatura. */
final class Ciudad {

    /** Las ciudades de la app y del widget, en el orden en que se muestran. */
    static final Ciudad[] TODAS = {
            new Ciudad("Chillán", "Ñuble, Chile", -36.6061, -72.1039),
            new Ciudad("San Nicolás", "Ñuble, Chile", -36.5000, -72.2167),
            new Ciudad("Galapagar", "Madrid, España", 40.5786, -4.0039),
    };

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
