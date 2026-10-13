package com.workwithplus.workwithplus_commongam;

/**
 * Reemplazo de WorkWithPlus_CommonGAM.SecGAMIsAuthByFunctionalityKey para la vista previa de pantallas de
 * GxPruebas: va primero en el classpath del motor de pantallas (no en el de Explorar ni las suites). Sin una
 * sesion de GAM el original niega todo y las pantallas esconden sus acciones (Insertar, Modificar, Eliminar).
 *
 * La propiedad gxp.permisos la pone el motor en cada pedido: "todos" (por defecto) o "ninguno".
 */
public final class secgamisauthbyfunctionalitykey {

   public secgamisauthbyfunctionalitykey(int remoteHandle) {
   }

   public secgamisauthbyfunctionalitykey(int remoteHandle, com.genexus.ModelContext context) {
   }

   public boolean executeUdp(String clave) {
      return !"ninguno".equals(System.getProperty("gxp.permisos", "todos"));
   }

   public void execute(String clave, boolean[] autorizado) {
      autorizado[0] = executeUdp(clave);
   }
}
