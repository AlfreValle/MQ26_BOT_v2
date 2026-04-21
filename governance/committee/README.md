# Comité de Auditoría — MQ26 BOT v2

Marco de gobernanza para revisión financiera y de código del sistema de trading automatizado.

---

## Orden de uso de plantillas

```
Primera vez / cambio de miembros
  └─ plantilla-mandato-y-composicion.md   ← define quiénes y bajo qué reglas

Cada ciclo de revisión (recomendado: semanal o tras cambio relevante)
  ├─ plantilla-agenda-reunion.md           ← convocar, adjuntar evidencias
  ├─ plantilla-checklist-auditoria-financiera.md
  ├─ plantilla-checklist-auditoria-codigo.md   ← alimentar con salida de audit.py
  ├─ plantilla-checklist-paso-a-live.md    ← solo antes de MODE=live
  └─ plantilla-acta-y-dictamen.md          ← copiar a dictamenes/ con nombre fechado

Incidentes
  └─ plantilla-postmortem-incidente.md     ← archivar como dictamenes/incidente-*.md
```

## Convención de nombres para dictámenes

```
dictamenes/AAAA-MM-DD_dictamen_<etiqueta>.md
```

Ejemplos:
- `2026-04-21_dictamen_operacion_demo.md`
- `2026-05-01_dictamen_paso_a_live.md`
- `2026-05-15_dictamen_cambio_capital_5000.md`

Una etiqueta por revisión. Nunca reutilizar un archivo ya firmado; crear uno nuevo.

## Cómo ejecutar la auditoría técnica

```bash
cd C:\Users\DELL\OneDrive\Documentos\MQ26_BOT\MQ26_BOT_v2

# Salida resumida (pegar en checklist-auditoria-codigo)
python audit.py

# Salida con detalles (para investigar WARNs / ERRORs)
python audit.py --verbose

# Markdown listo para la checklist (archivo por defecto)
python audit.py --export-md

# Markdown a stdout
python audit.py --export-md -
```

Pegar el bloque de texto (o el Markdown exportado) en la sección **Evidencia** del checklist de código.  
No pegar contenido del archivo `.env` ni credenciales.

## Numeración de dictámenes

```bash
python governance/new-dictamen.py paso_a_live
```

Crea `governance/committee/dictamenes/AAAA-NNN_dictamen_<etiqueta>.md` a partir de la plantilla de acta e intenta abrir el editor (`EDITOR` o Notepad en Windows).

## Funnel de señales (KPI)

Durante la operación, el bot escribe `data/logs/signal_funnel.json` con contadores acumulados en la sesión. Úsalo para rellenar la sección 10 del checklist financiero.

## Diffs en Git y GitHub

En `dictamenes/.gitattributes` los `.md` usan `linguist-documentation=true` y `diff=pandoc`.  
Para que `diff=pandoc` funcione en tu clon, hace falta configurar el driver (ejemplo):

```bash
git config diff.pandoc.textconv "pandoc --to=markdown"
git config diff.pandoc.cachetextconv true
```

Si no usas pandoc, Git seguirá mostrando diff línea a línea; no pasa nada.

## CODEOWNERS

En [.github/CODEOWNERS](../../.github/CODEOWNERS) sustituye `@TU_USUARIO_GITHUB` por el Secretario (o equipo).  
En GitHub activa **Require review from Code Owners** en la rama protegida para que los cambios bajo `dictamenes/` exijan revisión.

## Regla de secretos

> **Nunca** incluir en ningún archivo de esta carpeta:
> tokens de Telegram, contraseñas MT5, llaves de API, IDs de cuenta completos.
>
> Para referencias a cuenta usar solo los últimos 4 dígitos (p. ej. `…4499`).  
> Para tokens usar solo el prefijo de 6 caracteres seguido de `…` (p. ej. `123456…`).

## Trazabilidad git

Cada dictamen firmado se versiona automáticamente con `git add` + `git commit`.  
El historial de commits es el registro de auditoría inmutable.

```bash
git add governance/committee/dictamenes/
git commit -m "audit: dictamen 2026-04-21 operación demo — aprobado"
```

## Flujo de trabajo Git (ramas y PR)

Al **empezar una sesión de cambios** (código, `audit.py`, plantillas, etc.), crear rama desde `main` **antes** de tocar archivos:

```bash
git checkout main
git pull origin main
git checkout -b feat/nombre-mejora
# ... hacer cambios ...
git add ...
git commit -m "..."
git push -u origin feat/nombre-mejora
gh pr create --base main
```

- Sustituí `feat/nombre-mejora` por un nombre concreto (ej. `feat/signal-funnel`, `fix/mt5-spread`).
- **GitHub CLI:** hace falta tener [`gh`](https://cli.github.com/) instalado y haber ejecutado `gh auth login` al menos una vez. Si no usás `gh`, abrí el PR a mano en GitHub después del `push`.

## Archivos en esta carpeta

| Archivo | Propósito |
|---|---|
| `README.md` | Este índice |
| `plantilla-mandato-y-composicion.md` | Quiénes integran el comité y bajo qué reglas |
| `plantilla-agenda-reunion.md` | Convocatoria y puntos de revisión por sesión |
| `plantilla-checklist-auditoria-financiera.md` | Controles financieros manuales |
| `plantilla-checklist-auditoria-codigo.md` | Verificación 1:1 con las 10 capas de `audit.py` |
| `plantilla-checklist-paso-a-live.md` | Checklist antes de cuenta real |
| `plantilla-postmortem-incidente.md` | Post-mortem de incidentes |
| `plantilla-acta-y-dictamen.md` | Resolución y firma simbólica |
| `dictamenes/` | Dictámenes firmados, uno por ciclo de revisión |
| `dictamenes/.gitattributes` | Marcado linguist + diff opcional pandoc |
