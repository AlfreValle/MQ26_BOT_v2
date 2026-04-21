# Agenda de Reunión — Comité de Auditoría MQ26 BOT v2

> **Instrucciones:** Copiar este archivo por reunión.  
> Nombre sugerido: `agenda-AAAA-MM-DD.md` (no va en `dictamenes/`, es borrador).

---

## Encabezado

| Campo | Valor |
|---|---|
| **Fecha y hora** | `AAAA-MM-DD HH:MM UTC` |
| **Modalidad** | `[ ] Presencial` `[ ] Remota` `[ ] Asíncrona (comentarios en archivo)` |
| **Convocado por** | `________________` (Presidente) |
| **Tipo de revisión** | `[ ] Operativa semanal` `[ ] Capital mensual` `[ ] Código` `[ ] Extraordinaria` |

---

## Asistentes

| Rol | Nombre | Asistió |
|---|---|---|
| Presidente | `________________` | `[ ]` |
| Secretario | `________________` | `[ ]` |
| Experto financiero | `________________` | `[ ]` |
| Experto de código | `________________` | `[ ]` |
| Observador | `________________` | `[ ]` |

**Quorum:** `[ ] Alcanzado` `[ ] No alcanzado` → si no alcanzado, reunión pospuesta a `AAAA-MM-DD`.

---

## Declaración de conflictos de interés

> Cada asistente con interés en algún punto declara aquí antes de iniciar.

| Miembro | Punto conflictivo | Declarado |
|---|---|---|
| `________________` | `________________` | `[ ]` |
| — | — | — |

---

## Puntos de agenda

### Punto 1 — Apertura y verificación de quorum *(5 min)*

- [ ] Quorum confirmado
- [ ] Acta anterior aprobada (si aplica): `dictamenes/______.md`
- [ ] Conflictos de interés declarados

---

### Punto 2 — Estado del sistema desde la última revisión *(10 min)*

**Responsable:** Experto de código

- [ ] Bot corriendo sin interrupciones: `Sí / No — detalle: ________________`
- [ ] Watchdog activo: `Sí / No`
- [ ] Reinicios del bot en el periodo: `____ (ver watchdog.log)`
- [ ] Últimas modificaciones en código: commit `________________`
- [ ] Incidentes registrados: `Sí / No — detalle: ________________`

**Evidencia adjunta:**
```
[pegar aquí primeras líneas de data/logs/demo_trader.log del periodo, sin secretos]
```

---

### Punto 3 — Auditoría técnica (`audit.py`) *(15 min)*

**Responsable:** Experto de código  
**Instrucción:** Ejecutar `python audit.py` y pegar salida completa abajo.

- [ ] Ejecutado en: `AAAA-MM-DD HH:MM UTC`
- [ ] Versión de Python: `________________`
- [ ] Errores críticos `[ERROR!]`: `____`
- [ ] Advertencias `[ WARN ]`: `____`

**Salida completa de `audit.py`:**
```
[PEGAR AQUÍ — sin tokens ni contraseñas]
```

> Análisis detallado en `plantilla-checklist-auditoria-codigo.md`.

---

### Punto 4 — Revisión financiera *(15 min)*

**Responsable:** Experto financiero

- [ ] Balance MT5 revisado: `$________________`
- [ ] Equity MT5 revisado: `$________________`
- [ ] P&L del periodo: `+/- $________________` (`+/-____%`)
- [ ] Drawdown máximo del periodo: `____%`

> Análisis detallado en `plantilla-checklist-auditoria-financiera.md`.

---

### Punto 5 — Puntos extraordinarios *(si aplica)*

| # | Descripción | Responsable | Tiempo estimado |
|---|---|---|---|
| 5.1 | `________________` | `________________` | `__ min` |
| 5.2 | `________________` | `________________` | `__ min` |

---

### Punto 6 — Dictamen y resolución *(10 min)*

- [ ] Checklists financiera y de código completados y adjuntos
- [ ] Resolución propuesta: `[ ] Aprueba` `[ ] Aprueba con condiciones` `[ ] No aprueba`
- [ ] Votación registrada en acta
- [ ] Acta cerrada y guardada en `dictamenes/AAAA-MM-DD_dictamen_<etiqueta>.md`

---

### Punto 7 — Próxima reunión

- **Fecha propuesta:** `AAAA-MM-DD`
- **Tipo:** `________________`
- **Asignaciones antes de la próxima reunión:**

| Responsable | Tarea | Plazo |
|---|---|---|
| `________________` | `________________` | `AAAA-MM-DD` |

---

## Cierre

Reunión cerrada a las `HH:MM UTC`.  
Acta levantada por: `________________` (Secretario)
