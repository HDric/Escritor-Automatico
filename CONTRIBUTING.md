# Cómo contribuir

1. Abre una issue para describir el problema o la mejora, o busca una issue existente.
2. Crea una rama para los cambios.
3. Mantén los cambios centrados y no añadas ejecutables compilados ni dependencias vendorizadas.
4. Ejecuta las comprobaciones pertinentes antes de abrir un pull request:
   - `python -m py_compile escritor_automatico.py preflight.py preflight_linux.py`
   - comprueba el JSON de `web_extension/manifest.json`;
   - verifica que el identificador de la extensión coincida con el que espera la aplicación;
   - prueba, cuando sea posible, en Windows y Linux.
5. En el pull request explica los cambios, cómo probarlos y las limitaciones conocidas.

No incluyas datos personales, documentos reales, contraseñas, tokens ni logs con información sensible.
