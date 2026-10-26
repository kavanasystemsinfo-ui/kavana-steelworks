# Guía rápida del administrador

Para quien configura la empresa. Una pantalla: Admin, por pestañas.

## Empresa

Nombre mostrado, color principal y coste global de mano de obra (€/h). Ese
coste global se usa en los puestos que no tienen su propio coste/hora.

## Usuarios

Crea usuarios con su rol: operario, materias primas, supervisor o admin.
Cada rol ve solo su pantalla.

## Puestos

Código, nombre, grupo, coste hora (€) y método de registro. El coste hora es
la base del coste de mano de obra de las órdenes. Un puesto sin coste usa el
coste global de la empresa; sin ninguno de los dos, la mano de obra es 0 (no
se inventa).

## Secuencias

Prefijo, dígitos y siguiente número de las órdenes y de los lotes. La
numeración es automática y nunca repite número.

## Roles y permisos

Permisos por rol (escanear, vincular, producir, calidad, incidencias, OEE,
trazabilidad, administración).

## Productos

Catálogo de productos con su lista de materiales (BOM): piezas fabricadas y
materiales directos.

## Precios que necesita el coste

Para que el panel del supervisor muestre coste y estimado, configura:

- El €/kg estándar de cada material.
- El coste hora de cada puesto (o el coste global de la empresa).
