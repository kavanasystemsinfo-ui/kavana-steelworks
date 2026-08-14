# ADR-001: Clasificación del sistema: MES/MOM especializado en metalurgia

Estado: Aceptado
Fecha: 2026-08-14
Autor: Jorge Adán (KAVANA Systems)

## Contexto

Al preparar la reconstrucción del sistema (v2 → v4), surge una pregunta
fundamental que condiciona toda la documentación, el README y el posicionamiento
de portafolio: ¿qué es exactamente este sistema? Las opciones barajadas fueron
MES, MOM, ERP u otro tipo de sistema especializado en fábricas metalúrgicas.

La duda es legítima: el sistema nació de la experiencia real de un operario de
planta en fábricas metalúrgicas medianas y grandes, no de un libro de texto.
Por eso su alcance no coincide con la definición de catálogo de ninguna
categoría estándar.

## Decisión

El sistema se clasifica como **MES (Manufacturing Execution System) con alcance
MOM (Manufacturing Operations Management)**, especializado en la transformación
de bobinas de acero en el sector metalúrgico.

Según el estándar ISA-95, la capa de operaciones (nivel 3) cubre cuatro
actividades. Este sistema implementa las cuatro:

| Actividad ISA-95 | Módulos del sistema | Estado |
|---|---|---|
| Producción | Órdenes de fabricación, turnos A-B-C, OEE, planificación por puesto | ✅ |
| Calidad | Autocontroles ISO 9001, registros de calidad, trazabilidad | ✅ |
| Mantenimiento | Incidencias, averías, cierre financiero de paradas | ✅ |
| Inventario | Bobinas, stock, FIFO con burbuja de vinculación, retales | ✅ |

Además incorpora dos capacidades que exceden el MES de catálogo:

1. **Reconciliación industrial**: motor de consumo físico (geometría x densidad
   calibrada 7.7807 kg/dm³) que hace coincidir los kilos declarados con las
   básculas reales de planta.
2. **Coste real vs estimado**: cálculo de coste por orden con consumo real de
   material, merma y horas, cerrando el lazo entre ejecución y rentabilidad.

## Por qué no es un ERP

Un ERP (Enterprise Resource Planning) gestiona recursos empresariales a nivel
de compañía: finanzas, contabilidad, compras, RRHH, planificación maestra de
recursos. Este sistema no gestiona ninguna de esas áreas: no hay libro mayor,
ni nóminas, ni aprovisionamiento. Su frontera es la planta, no la empresa.

## Por qué no es solo un "MES genérico"

La mayoría de MES comerciales se venden como plataformas configurables para
cualquier industria. Este sistema está calibrado para un problema físico
concreto: el control de bobinas de acero, su consumo FIFO real por puesto de
trabajo y la reconciliación de merma al cierre de turno. Esa especificidad es
su valor, no su limitación.

## Término recomendado para uso público

En el CV, README y comunicaciones: **"MES/MOM para el sector metalúrgico"**.
Es honesto (refleja el estándar ISA-95), reconocible por reclutadores técnicos
y no sobrevende (no es un ERP).

## Consecuencias

- Toda la documentación nueva usará el término MES/MOM metalúrgico.
- El README explicará el origen: diseñado por un operario de planta real.
- La reconstrucción preservará las 4 actividades ISA-95 como frontera funcional.
- No se añadirán módulos de ERP (finanzas, RRHH) salvo petición explícita: YAGNI.
