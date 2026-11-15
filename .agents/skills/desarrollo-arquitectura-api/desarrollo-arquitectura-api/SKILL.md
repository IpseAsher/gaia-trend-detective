---
name: desarrollo-arquitectura-api
description: >-
  Diseña, implementa y revisa APIs HTTP/REST sobre HTTPS con semántica IETF y contratos OpenAPI.
  Úsala para modelar recursos y operaciones, revisar endpoints, contratos, errores,
  autenticación, autorización, caché, paginación, idempotencia, versionado, migraciones
  y pruebas de contrato, o para evaluar el estilo de API apropiado.
---

# Desarrollo y arquitectura de APIs

## Delimitar el problema

- Identifica consumidores, operaciones, límites de dominio, datos sensibles y compromisos de compatibilidad, latencia y disponibilidad. Si faltan datos, explicita los supuestos que condicionan el diseño y avanza con decisiones reversibles.
- Revisa los contratos, rutas, middleware, esquemas, pruebas y convenciones existentes. Usa el contrato publicado o la evidencia del comportamiento desplegado para identificar qué pueden esperar los clientes actuales.
- Si tienes que elegir un estilo, evalúa requisitos concretos de interoperabilidad, streaming, asincronía y herramientas del equipo. Aplica las reglas de HTTP a la interfaz HTTP y verifica la especificación propia de cualquier otro protocolo o estilo elegido.

## Definir el contrato HTTP

- Define recursos y operaciones según el dominio. Fija método, URI, parámetros, cabeceras, tipos de contenido, esquemas y respuestas observables. Marca como decisiones de diseño las convenciones de rutas, paginación y versionado.
- Aplica RFC 9110 a seguridad e idempotencia de métodos, negociación y respuestas. Mantén GET para lectura. Usa 201 al crear recursos y documenta cómo localizarlos. Usa 202 cuando el procesamiento aún está pendiente y define cómo consultar el resultado. En 204 omite el cuerpo.
- Distingue autenticación requerida (401 con el desafío aplicable) de acceso denegado (403). Documenta cuándo la política permite ocultar la existencia de un recurso con 404. Diferencia los conflictos con el estado actual (409) de las precondiciones de solicitud incumplidas (412).
- Si el contrato adopta RFC 9457, usa application/problem+json y tipos estables. Mantén status coherente con la respuesta HTTP cuando se incluya. Usa extensiones documentadas para errores de campo y evita exponer detalles internos o datos sensibles.
- Elige la versión de OpenAPI que soporte la cadena real de validadores, documentación y generación de clientes. Declara parámetros, esquemas por respuesta, variantes de error y requisitos de seguridad por operación. Incluye ejemplos sintéticos coherentes con el esquema. Comprueba que el contrato y la implementación describen el mismo comportamiento.

## Diseñar operación, seguridad y evolución

- Publica los endpoints de producción por HTTPS y decláralos con URLs https:// en OpenAPI. Prefiere TLS 1.3 y conserva TLS 1.2 solo si lo exige la compatibilidad, con la configuración de RFC 9325. Verifica la cadena de confianza y el nombre de host en clientes. Evita recibir credenciales o datos sensibles por HTTP y verifica el transporte entre el proxy y el servicio según el límite de confianza.
- Define quién puede realizar cada operación sobre cada objeto y propiedad. Aplica autorización en el servidor, también para listados y mutaciones. Valida entradas, limita tamaño, volumen y tiempo de procesamiento, y filtra los campos de salida según el contrato. Si se usa OAuth 2.0, contrasta el flujo y sus controles con el RFC 9700.
- Documenta presupuesto de reintentos y tiempos de espera. Define cuáles operaciones admiten reintento sin duplicar efectos. Si negocias una clave de idempotencia para escrituras, define alcance, vigencia, respuesta a repeticiones y tratamiento de solicitudes concurrentes o con contenido distinto. Protege la escritura con un mecanismo atómico y verifica recuperación tras fallos parciales.
- Define orden estable y desempate en paginación. Documenta el alcance de los cursores, los límites y qué ocurre si cambian los datos entre páginas. Para límites de solicitudes, documenta 429 y Retry-After cuando lo uses.
- Define la caché de acuerdo con RFC 9111 y con la sensibilidad de la respuesta. Cuando corresponda, usa validadores como ETag para revalidación y precondiciones como If-Match para prevenir actualizaciones perdidas.
- Evalúa compatibilidad de solicitudes, respuestas y semántica, incluidos cambios en campos requeridos, significado, valores enumerados y errores. Considera clientes generados y consumidores estrictos. Para cambios incompatibles, define transición, convivencia y retiro según el contrato y la política del equipo.
- Para operaciones críticas, define trazabilidad, métricas de latencia y errores, y señales operativas útiles. Evita credenciales y contenido sensible en registros y trazas. Ajusta la arquitectura a los requisitos observables de la tarea.

## Implementar y verificar

1. Si pidieron cambios, actualiza contrato, implementación y comprobaciones relacionadas. Reutiliza mecanismos del repositorio y preserva las garantías que el cambio no modifica.
2. Ejecuta los validadores disponibles y las pruebas pertinentes desde las entradas normales de la API. Comprueba respuestas exitosas, validación, denegación de acceso y errores. Añade cobertura de concurrencia, reintentos o compatibilidad cuando el cambio introduzca un riesgo específico y falten pruebas.
3. En revisiones, cita ruta, operación y evidencia concreta. Ordena hallazgos según impacto en consumidores, integridad de datos y operación. Indica qué rompe, bajo qué condiciones y cómo verificar la corrección.
4. Entrega el contrato o diff solicitado, registra las decisiones con consecuencias para consumidores y resume las comprobaciones realizadas. Indica qué quedó sin verificar.

## Fuentes primarias

- Semántica HTTP, métodos, estados y precondiciones. [IETF RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
- Configuración segura de TLS. [IETF RFC 9325](https://www.rfc-editor.org/rfc/rfc9325.html)
- Caché HTTP y revalidación. [IETF RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html)
- Formato de errores HTTP. [IETF RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
- Estados HTTP adicionales, incluido 429. [IETF RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html)
- Práctica recomendada de seguridad OAuth 2.0. [IETF RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- Versiones y reglas de los contratos OpenAPI. [OpenAPI Initiative](https://spec.openapis.org/oas/)
- Guía complementaria de riesgos para la revisión defensiva. [OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
