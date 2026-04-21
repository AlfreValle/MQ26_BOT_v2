# Acta y Dictamen — Comité de Auditoría MQ26 BOT v2

> **Instrucciones:** Copiar este archivo a `dictamenes/AAAA-MM-DD_dictamen_<etiqueta>.md`  
> una vez completado. No modificar este archivo plantilla.  
> El archivo copiado es el registro inmutable; commitear con git.

---

## Identificación del dictamen

| Campo | Valor |
|---|---|
| **Número de dictamen** | `____` (secuencial por año, p. ej. `2026-003`) |
| **Fecha de emisión** | `AAAA-MM-DD` |
| **Periodo auditado** | `AAAA-MM-DD` al `AAAA-MM-DD` |
| **Tipo de revisión** | `[ ] Operativa semanal` `[ ] Capital mensual` `[ ] Código` `[ ] Paso a Live` `[ ] Extraordinaria` |
| **Commit auditado** | `________` (`git rev-parse --short HEAD`) |
| **Cuenta** | IC Markets …`____` |
| **Modalidad** | `[ ] Demo` `[ ] Live` |
| **Mejoras activas en código** | Lista de IDs o referencia a CHANGELOG (ej. `#77, #80, #86…`) → `________________` |

> Sugerencia: `git log -1 --oneline` + convención de mejoras en `demo_trader.py`, o lista manual desde el CHANGELOG del repo.

---

## Asistentes con voto

| Rol | Nombre | Voto emitido |
|---|---|---|
| Presidente | `________________` | `[ ] Aprueba` `[ ] Aprueba con condiciones` `[ ] No aprueba` `[ ] Abstención` |
| Experto financiero | `________________` | `[ ] Aprueba` `[ ] Aprueba con condiciones` `[ ] No aprueba` `[ ] Abstención` |
| Experto de código | `________________` | `[ ] Aprueba` `[ ] Aprueba con condiciones` `[ ] No aprueba` `[ ] Abstención` |

**Conflictos de interés declarados:** `Ninguno / ________________`

---

## Documentos revisados en esta sesión

| Documento | Completado | Hallazgos |
|---|---|---|
| `plantilla-checklist-auditoria-financiera.md` | `[ ] Sí` `[ ] No` | `Sin hallazgos / WARN / ERROR` |
| `plantilla-checklist-auditoria-codigo.md` | `[ ] Sí` `[ ] No` | `Sin hallazgos / WARN / ERROR` |
| Salida de `python audit.py` | `[ ] Sí` `[ ] No` | `____` errores / `____` warnings |
| Extracto de `demo_trader.log` | `[ ] Sí` `[ ] No` | — |
| Otros: `________________` | `[ ] Sí` `[ ] No` | — |

---

## Resumen de hallazgos

### Hallazgos financieros

| # | Severidad | Descripción | Ítem de checklist |
|---|---|---|---|
| F-1 | `[ ] INFO` `[ ] WARN` `[ ] ERROR` | `________________` | Sección `____` |
| F-2 | `[ ] INFO` `[ ] WARN` `[ ] ERROR` | `________________` | Sección `____` |

*(agregar filas según necesidad; eliminar las vacías antes de firmar)*

### Hallazgos de código

| # | Severidad | Descripción | Capa `audit.py` |
|---|---|---|---|
| C-1 | `[ ] INFO` `[ ] WARN` `[ ] ERROR` | `________________` | Capa `____` |
| C-2 | `[ ] INFO` `[ ] WARN` `[ ] ERROR` | `________________` | Capa `____` |

*(agregar filas según necesidad)*

---

## Deliberación

> Espacio para registrar los argumentos principales discutidos antes de votar.

```
________________
```

---

## Resolución

### Resultado de votación

| Opción | Votos |
|---|---|
| Aprueba | `____` |
| Aprueba con condiciones | `____` |
| No aprueba | `____` |
| Abstención | `____` |

### Dictamen oficial

```
[ ] APRUEBA
    El sistema MQ26 BOT v2 puede continuar operando sin restricciones
    durante el siguiente periodo de revisión.

[ ] APRUEBA CON CONDICIONES
    El sistema puede continuar operando sujeto a las condiciones listadas
    en la sección "Plan de acción" (ver abajo). Las condiciones deben
    subsanarse antes de la próxima reunión.

[ ] NO APRUEBA
    El sistema debe detenerse hasta subsanar los errores críticos
    identificados. Fecha de re-evaluación: AAAA-MM-DD.
```

**Justificación:**
```
________________
```

---

## Plan de acción (si aplica)

> Completar solo si el dictamen es "Aprueba con condiciones" o "No aprueba".

| # | Acción requerida | Responsable | Plazo | Estado |
|---|---|---|---|---|
| 1 | `________________` | `________________` | `AAAA-MM-DD` | `[ ] Pendiente` `[ ] Completado` |
| 2 | `________________` | `________________` | `AAAA-MM-DD` | `[ ] Pendiente` `[ ] Completado` |
| 3 | `________________` | `________________` | `AAAA-MM-DD` | `[ ] Pendiente` `[ ] Completado` |

---

## Próxima revisión

| Campo | Valor |
|---|---|
| **Fecha propuesta** | `AAAA-MM-DD` |
| **Tipo** | `[ ] Operativa semanal` `[ ] Capital mensual` `[ ] Código` `[ ] Extraordinaria` |
| **Condición de convocatoria anticipada** | `Kill switch activo / DD > 2% / cambio de código crítico / otro: ________________` |

---

## Firma simbólica

> La firma simbólica (nombre + fecha) en un repositorio git tiene equivalencia práctica  
> al historial de commits. No se requiere firma criptográfica.

| Rol | Nombre | Fecha | Firma |
|---|---|---|---|
| **Presidente** | `________________` | `AAAA-MM-DD` | `________________` |
| **Secretario** | `________________` | `AAAA-MM-DD` | `________________` |
| **Experto financiero** | `________________` | `AAAA-MM-DD` | `________________` |
| **Experto de código** | `________________` | `AAAA-MM-DD` | `________________` |

---

## Control de versiones de este dictamen

| Versión | Fecha | Autor | Cambio |
|---|---|---|---|
| 1.0 | `AAAA-MM-DD` | `________________` | Emisión inicial |
| 1.1 | `AAAA-MM-DD` | `________________` | Corrección: `________________` |

---

*Archivado en:* `governance/committee/dictamenes/AAAA-MM-DD_dictamen_<etiqueta>.md`  
*Commit de archivo:* `________`
