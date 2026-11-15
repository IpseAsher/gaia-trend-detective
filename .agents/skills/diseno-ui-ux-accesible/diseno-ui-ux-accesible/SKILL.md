---
name: diseno-ui-ux-accesible
description: >-
  Diseña, implementa y evalúa interfaces y recorridos web con WCAG 2.2 AA y buenas
  prácticas de usabilidad. Úsala para prototipos, auditorías UI/UX, diseño adaptable,
  formularios, navegación, componentes, sistemas de diseño y pruebas de accesibilidad.
---

# Diseño UI/UX accesible

## Definir la tarea

- Identifica quién usa la interfaz, qué necesita lograr y cómo sabrá que terminó. Aclara los dispositivos, idiomas y restricciones que cambian el diseño. Declara como hipótesis las necesidades que aún no se hayan investigado.
- Revisa el recorrido y los componentes existentes. Conserva patrones familiares y reutiliza tokens y componentes que cubran el comportamiento requerido. Si un componente compartido tiene un defecto, estima el alcance de corregirlo en origen.
- Para una creación, define el recorrido principal, su punto de entrada y su salida. Para una auditoría, selecciona páginas, estados y procesos representativos. Usa WCAG 2.2 nivel AA como objetivo web, incluidos los criterios de nivel A.

## Diseñar el recorrido y la interfaz

- Ordena contenido y acciones según la intención del usuario. Da prioridad visual a la acción principal de cada paso. Usa texto concreto y consistente, etiquetas visibles, jerarquía tipográfica y espaciado que reflejen agrupaciones. Revisa con contenido realista, textos largos y datos vacíos.
- Diseña con flexibilidad para distintos anchos, zoom, texto ampliado y orientación. Mantén alineación, densidad y lectura adecuadas para la tarea. Haz que el orden visual, de lectura y de interacción sean coherentes.
- Diseña los estados que el flujo realmente puede presentar. Incluye carga, éxito, vacío y error cuando correspondan. Indica qué pasó y cuál es el siguiente paso. Conserva los datos válidos tras un error y ofrece deshacer, revisar o confirmar cuando las consecuencias lo justifiquen.
- Usa las heurísticas de Nielsen para localizar fricción. Examina visibilidad del estado, consistencia, prevención de errores, control del usuario y carga de memoria. Para contrastar hipótesis, observa a personas representativas, incluidas personas con discapacidad, ejecutar tareas con objetivos realistas. Registra si completan la tarea, dónde se atascan y cuánta ayuda requieren.

## Aplicar WCAG 2.2 AA

Usa la recomendación de W3C para determinar qué criterios aplican al recorrido completo. Empieza por estas comprobaciones frecuentes.

| Área | Comprobaciones |
| --- | --- |
| Percepción | Proporciona alternativas textuales según la función de imágenes y controles, y subtítulos o audiodescripción cuando aplique. Evita transmitir información solo con color (1.1.1, 1.2, 1.4.1). |
| Contraste | Mide colores efectivos. Aplica 4.5 a 1 al texto normal y 3 a 1 al texto grande. Aplica 3 a 1 a la información visual necesaria de controles, estados y gráficos frente a colores adyacentes, según las excepciones del criterio (1.4.3, 1.4.11). |
| Texto y adaptación | Comprueba texto al 200 %, cambios de espaciado y reflujo a un ancho equivalente a 320 px CSS para contenido de desplazamiento vertical. Conserva información y funcionalidad sin desplazamiento en dos direcciones salvo las excepciones aplicables (1.4.4, 1.4.10, 1.4.12). |
| Teclado y foco | Completa la tarea con teclado, sin trampas. Revisa orden lógico, foco visible y elementos enfocados que no queden totalmente ocultos por contenido creado por la página (2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11). |
| Puntero | Ofrece una alternativa de puntero sin arrastrar cuando aplique. Usa objetivos de al menos 24 × 24 px CSS o documenta la excepción aplicable, como el espaciado suficiente (2.5.7, 2.5.8). |
| Formularios y acceso | Asocia etiquetas e instrucciones, identifica el error y sugiere cómo corregirlo cuando corresponda. Evita solicitar de nuevo información del mismo proceso cuando aplique. Revisa autenticación accesible y compatibilidad con gestores de contraseñas y pegado (3.3.1–3.3.3, 3.3.7, 3.3.8). |
| Semántica y avisos | Usa encabezados, regiones y controles nativos adecuados. Comprueba nombre, rol, estado y valor accesibles. Anuncia avisos dinámicos pertinentes sin mover el foco, cuando corresponda (1.3.1, 4.1.2, 4.1.3). |

Prefiere HTML nativo. Para componentes personalizados, consulta ARIA APG y verifica su semántica, interacción con teclado y gestión de foco en las combinaciones relevantes de navegador y tecnología de asistencia.

## Verificar y entregar

1. Recorre la tarea completa en móvil y escritorio con contenido representativo. Incluye estados de error y recuperación. Usa capturas cuando ayuden a mostrar problemas visuales y conserva una referencia a la ubicación del hallazgo.
2. Combina las herramientas automáticas disponibles con pruebas manuales de teclado, foco, zoom y contraste. Si puedes usar un lector de pantalla, anota navegador, lector y comprobaciones realizadas. Una maqueta estática permite evaluar aspectos visuales y estructura prevista. Verifica interacción y semántica en la implementación.
3. Para cada hallazgo, indica pantalla o componente, estado y condiciones, evidencia, impacto en la tarea, cambio propuesto y cómo verificarlo. Cita el identificador WCAG solo cuando corresponda. Prioriza primero lo que bloquea un recorrido, luego lo que dificulta completarlo.
4. Informa qué páginas, procesos y estados comprobaste, qué herramientas o métodos usaste y qué quedó pendiente. Reserva una declaración de conformidad para una evaluación que cubra el alcance declarado, páginas completas, procesos completos y requisitos de conformidad de WCAG. Una auditoría automática por sí sola aporta evidencia parcial.

## Fuentes

- Criterios normativos y requisitos de conformidad. [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- Semántica e interacción de componentes personalizados. [W3C ARIA APG](https://www.w3.org/WAI/ARIA/apg/)
- Métodos de evaluación de accesibilidad. [W3C WAI](https://www.w3.org/WAI/test-evaluate/)
- Pruebas de tareas con usuarios. [GOV.UK Service Manual](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing)
- Mensajes de error y recuperación en formularios. [GOV.UK Design System](https://design-system.service.gov.uk/components/error-message/)
- Revisión heurística de interacciones. [Nielsen Norman Group](https://www.nngroup.com/articles/ten-usability-heuristics/)
