# Corrección de publicación de GitHub Release — v1.0.2

## Problema corregido

El trabajo `publish-release` asumía que los archivos descargados de Actions estaban directamente en `release-assets/windows/` y `release-assets/linux/`. `actions/upload-artifact` conserva parte de la estructura de carpetas de los archivos subidos, por lo que los instaladores pueden quedar dentro de subcarpetas como `dist-installer/`, `security-artifacts/` o `dist-linux/`.

## Cambio

El workflow ahora busca cada artefacto por su nombre exacto dentro de las carpetas descargadas, exige encontrar exactamente una coincidencia e imprime el contenido disponible si falta algún archivo. Después copia los resultados a `release-assets/final/` y continúa con la generación de SHA-256 y la firma Ed25519.

## Cómo aplicar

1. Aplica `build-installer.yml` en `.github/workflows/build-installer.yml`.
2. Incorpora el cambio en `main` mediante un Pull Request, respetando la protección de la rama.
3. Como `v1.0.2` ya existe pero la publicación falló antes de crear la Release, verifica en GitHub que no exista una Release `v1.0.2` publicada.
4. Una vez integrado el arreglo en `main`, actualiza la etiqueta `v1.0.2` para que apunte al nuevo commit y vuelve a ejecutar el flujo de publicación. La forma más simple es borrar la etiqueta remota/local fallida y recrearla en el nuevo `main` (solo porque esta publicación no llegó a crear una Release). No hagas esto si ya existe una Release pública con ese tag.

## Seguridad

No incluye claves privadas ni secretos. El paso de firma Ed25519 y la validación de `version.json` se mantienen.
