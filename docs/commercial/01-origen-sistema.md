# Origen del sistema: la historia de por qué existe

> **Borrador para revisión de Jorge.** Narrativa de portafolio basada en
> experiencia real verificada: 8 años en fábricas metalúrgicas (CNC, turnos),
> varias empresas medianas y grandes, sin nombres inventados. Revisar antes
> de publicar en README público, landing o LinkedIn.

## El punto de partida: 8 años dentro de la fábrica

Este sistema no nació en un aula ni en un despacho de consultoría. Nació en el
suelo de la fábrica, del día a día de 8 años trabajando como operario en
fábricas metalúrgicas de distintos tamaños: CNC, líneas de producción, turnos
de mañana, tarde y noche.

En ese tiempo se ven cosas que nadie desde fuera puede ver. Se ve cómo se
pierde el tiempo, dónde se pierde, y cuánto cuesta en dinero real.

## Los problemas que se ven desde dentro

### El papel como sistema de gestión

En varias plantas, la producción se gobernaba con hojas de papel. El operario
anotaba a mano lo que producía, el material que consumía, las incidencias. Esas
hojas acababan en una carpeta, o en una caja, o se perdían. Al final del turno
o de la semana, alguien intentaba reconstruir qué había pasado realmente.

El resultado era siempre el mismo: datos incompletos, kilos que no cuadraban,
mermas que nadie sabía explicar, y horas de supervisores transcribiendo papel a
Excel.

### Las hojas de cálculo como sistema de trazabilidad

El Excel era el siguiente nivel: mejor que el papel, pero con los mismos
problemas de fondo. Una hoja por planta, otra por turno, otra por material.
Fórmulas que alguien tocaba sin querer. Versiones que se pisaban. Y sobre todo:
el dato se escribía **después** de que pasara la acción, nunca durante.

Cuando un operario consume una bobina de acero y nadie lo registra en el
momento, ese kilo desaparece del inventario físico aunque esté en la máquina.
A final de mes, el stock no cuadra y nadie sabe decir por qué.

### Los sistemas no automatizados

En las empresas donde había software, muchas veces era un ERP pensado para la
oficina, no para la planta. El operario no lo tocaba, el supervisor apuntaba y
luego transcribía. La distancia entre lo que pasaba en la máquina y lo que
decía el sistema era de horas o días. Para una fábrica, horas de retraso en el
dato son pérdidas de dinero que nadie ve.

## Lo que sí funcionaba (y que este sistema replica)

No todo era malo. Había cosas que funcionaban bien y que merecían la pena:

- El operario que conocía su máquina y sabía cuánto producía de verdad.
- El supervisor que detectaba una caída de rendimiento con solo mirar la línea.
- La disciplina de ciertas plantas con sus partes de producción diarios.
- El conocimiento tácito de cómo se consume una bobina, cómo se aprovecha un
  retal, cuándo una merma es real y cuándo es un error de registro.

Este sistema no se inventó contra la fábrica: se construyó **desde** la
fábrica, replicando lo que funcionaba y eliminando lo que perdía tiempo.

## Lo que este sistema aporta (visto desde dentro)

### El dato en el momento, no después

El operario registra su producción y su consumo de material en el momento, con
una tablet y un escáner, en su puesto de trabajo. No hay papel, no hay
transcripción, no hay doble tecleo. El dato entra una sola vez, donde ocurre.

### El material que cuadra con la báscula

El motor de consumo FIFO con "burbuja de vinculación" resuelve el problema que
ningún Excel puede resolver: saber qué bobina concreta se está consumiendo en
cada orden, en cada puesto, y que los kilos declarados coincidan con el
material físico. La densidad se calibró contra básculas reales de planta
(constante 7.7807 kg/dm³). No es un ratio teórico: es física aplicada al
inventario.

### El turno como unidad de verdad

En la fábrica el tiempo se mide en turnos, no en horas. El sistema estructura
la producción en turnos A-B-C (mañana, tarde, noche), el idioma natural de
planta, y calcula OEE en tiempo real con la velocidad teórica de cada modelo.

### La calidad sin interrumpir el trabajo

Los autocontroles ISO 9001 se piden con avisos no bloqueantes, a los 15
minutos de empezar la jornada y luego cada 2 horas. El operario no pierde el
hilo de su trabajo, y la trazabilidad queda registrada sin fricción.

### El supervisor con un vistazo

El panel del supervisor muestra en una sola pantalla lo que antes exigía
recorrer la planta o esperar al informe de fin de semana: producción por turno,
OEE, mermas, coste real contra estimado, incidencias en tiempo real y alertas
de parada prolongada.

## Qué es este sistema, en una frase

Un sistema de ejecución de manufactura (MES) con alcance de gestión de
operaciones (MOM), especializado en fábricas metalúrgicas que trabajan con
bobinas de acero, diseñado por alguien que vivió los problemas que resuelve.

No es un ERP. No es un software de oficina adaptado a planta. Es software
construido desde la planta, por un operario que pasó 8 años viendo dónde se
perdía el tiempo y el material, y que decidió replicar lo que funcionaba y
arreglar lo que no.

## Notas para el portafolio

- La historia es real y verificable en la experiencia laboral de Jorge
  (8 años en metalurgia, CNC, turnos, varias empresas, sin nombres).
- No se inventan empresas, clientes ni anécdotas específicas.
- El tono es el de un ingeniero de producto con experiencia de planta, no el
  de un consultor vendiendo humo.
- Esta narrativa alimenta: README público, landing del proyecto, caso de
  estudio, post de LinkedIn y respuestas en entrevistas.
