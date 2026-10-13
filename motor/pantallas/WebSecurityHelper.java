package com.genexus.security.web;

/**
 * Reemplazo de WebSecurityHelper para el motor de pantallas de GxPruebas (va primero en su classpath; no en el
 * de Explorar ni las suites). GeneXus firma con un token que vence los valores que la pagina no puede cambiar
 * (gxhash_*), el permiso para llamar eventos (X-GXAUTH-TOKEN) y otros. Aca la firma es siempre la misma y la
 * verificacion siempre pasa: un pedido grabado en la vista previa se puede repetir igual dias despues (los pasos
 * "pantalla" de las suites). Es un entorno de pruebas: no hay usuarios ni nada que proteger.
 */
public class WebSecurityHelper {

   public static final String FIRMA = "gxpruebas";

   public static String sign(String pgm, String issuer, String value, SecureTokenHelper.SecurityMode mode, String key) {
      return FIRMA;
   }

   public static boolean verify(String pgm, String issuer, String value, String token, String key) {
      return true;
   }
}
