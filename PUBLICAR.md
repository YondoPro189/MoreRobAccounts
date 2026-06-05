# Publicar MoreRobAccounts para otros usuarios

## 1. Crear el paquete listo para descargar

Doble clic en **`make_release.bat`** (o desde PowerShell):

```powershell
cd "C:\Users\yondo\OneDrive\Documentos\MoreRobAccounts"
.\make_release.bat
```

Genera:
- `release\MoreRobAccounts-v1.0-win64\` — carpeta para compartir
- `release\MoreRobAccounts-v1.0-win64.zip` — archivo para subir

Contenido del paquete:
| Archivo | Para qué |
|---------|----------|
| `MoreRobAccountsUI.exe` | La aplicación (sin consola) |
| `accounts.json` | Vacío; cada usuario guarda sus cuentas aquí |
| `LEEME.txt` | Instrucciones para quien lo descarga |

> **No incluyas tu `accounts.json` personal** en el ZIP (tiene tus sesiones cifradas).

---

## 2. Dónde subirlo para que otros lo descarguen

### GitHub Releases (recomendado, gratis)
1. Crea un repo en GitHub (puede ser privado o público).
2. Sube el código fuente (sin `accounts.json`, sin `dist/`).
3. Ve a **Releases** → **Create a new release**.
4. Adjunta `MoreRobAccounts-v1.0-win64.zip`.
5. Comparte el link de la release.

### Google Drive / OneDrive
1. Sube el `.zip`.
2. Clic derecho → **Obtener enlace** / **Compartir**.
3. Permiso: **Cualquier persona con el enlace**.

### Discord / Telegram
Puedes enviar el ZIP directamente (límite de tamaño ~8–50 MB según plataforma).

---

## 3. Qué deben hacer quienes lo descargan

1. Descomprimir el ZIP.
2. Ejecutar `MoreRobAccountsUI.exe`.
3. Agregar sus cuentas y lanzar Roblox.

Tener **Roblox instalado** en Windows es obligatorio.

---

## 4. Avisos importantes al distribuir

| Tema | Qué esperar |
|------|-------------|
| **SmartScreen** | Windows puede decir "desconocido". Normal sin certificado de firma (~$200/año). |
| **Antivirus** | Posibles falsos positivos (PyInstaller). Avisa en el LEEME. |
| **Login por navegador** | En el `.exe` puede usar Edge del sistema; si falla, pegar cookie (avanzado). |
| **Solo Windows** | No funciona en Mac/Linux. |
| **Roblox ToS** | Multi-cuenta puede ir contra las reglas de Roblox; distribuye bajo tu responsabilidad. |

---

## 5. Mejorar confianza (opcional)

- **Firmar el .exe** con certificado de código (EV/OV) → menos alertas de Windows.
- **Publicar código fuente** en GitHub para que otros vean qué hace.
- **VirusTotal**: sube el `.exe` y comparte el link del análisis.

---

## 6. Actualizar versión

1. Cambia `VERSION=1.0` en `make_release.bat` (ej. `1.1`).
2. Vuelve a ejecutar `make_release.bat`.
3. Sube el nuevo ZIP como release.
