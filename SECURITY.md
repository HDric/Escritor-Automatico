# Política de seguridad

## Versiones mantenidas

Las correcciones de seguridad se aplican primero a la versión estable más reciente. Las versiones antiguas pueden dejar de recibir correcciones; se recomienda actualizar desde una Release oficial y revisar su manifiesto `SHA256SUMS.txt` y la firma `SHA256SUMS.txt.sig`.

## Reportar una vulnerabilidad

No publiques detalles explotables en issues, discusiones ni pull requests. Usa **Report a vulnerability** en la pestaña Security del repositorio (GitHub Private Vulnerability Reporting) cuando esté habilitado. Si no está disponible, contacta privadamente con el mantenedor antes de divulgar el problema.

Incluye, cuando sea seguro: versión afectada, sistema operativo, componente, impacto y pasos mínimos para reproducir. No envíes contraseñas, tokens, claves privadas, datos personales ni documentos reales.

No existe un plazo de respuesta o resolución garantizado. El mantenedor confirmará recepción cuando sea posible y coordinará la divulgación responsable.

## Uso y límites

Revisa `INFORME_SEGURIDAD.md` y `web_extension/manifest.json` antes de instalar. El puente local requiere emparejar manualmente la extensión con un código secreto de 256 bits. No compartas ese código ni ejecutes la aplicación como administrador/root.

Las pruebas automatizadas, SBOMs y auditorías de dependencias reducen riesgos, pero no constituyen garantía de ausencia de vulnerabilidades. Los paquetes publicados se distribuyen sin firma Authenticode del ejecutable de Windows; la firma Ed25519 del manifiesto autentica los artefactos frente a la clave pública incluida en la aplicación.
