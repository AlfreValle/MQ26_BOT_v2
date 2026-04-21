# Mandato y Composición del Comité — MQ26 BOT v2

> **Instrucciones:** Completar una sola vez (o cada vez que cambie un miembro).  
> Guardar el archivo completado con nombre `mandato-vigente.md` en esta misma carpeta.

---

## 1. Identificación

| Campo | Valor |
|---|---|
| **Nombre del sistema** | MQ26 BOT v2 |
| **Cuenta operada** | IC Markets …`____` (últimos 4 dígitos) |
| **Modalidad actual** | `[ ] Demo` `[ ] Live` |
| **Fecha de vigencia de este mandato** | `AAAA-MM-DD` |
| **Sustituye al mandato de** | `AAAA-MM-DD` / `N/A (primer mandato)` |

---

## 2. Objetivo del comité

El comité tiene por objeto revisar periódicamente que el sistema MQ26 BOT v2:

1. Opere dentro de los límites de riesgo acordados (capital, drawdown, tamaño de posición).
2. Funcione conforme a la lógica de código documentada (estrategia S03, protecciones M72–M136).
3. Mantenga trazabilidad de operaciones (logs, journal, dictámenes).
4. Identifique desviaciones antes de que impacten el capital.

---

## 3. Alcance

### Incluido
- Revisión financiera: balance, equity, P&L diario/semanal, drawdown, fees/spread.
- Revisión de código: salida de `audit.py` + verificación manual de protecciones.
- Revisión de procesos: arranque, watchdog, PID lock, cierre semanal.

### Excluido
- Optimización de parámetros de estrategia (responsabilidad del desarrollador).
- Infraestructura externa a MT5 (bróker, conectividad de red).
- Decisiones de aumento de capital (requieren proceso separado).

---

## 4. Composición y roles

| Rol | Nombre | Responsabilidades principales |
|---|---|---|
| **Presidente** | `________________` | Convoca reuniones, dirige agenda, firma dictamen. |
| **Secretario** | `________________` | Levanta acta, archiva dictámenes en `dictamenes/`. |
| **Experto financiero** | `________________` | Completa `checklist-auditoria-financiera`, revisa P&L y riesgo. |
| **Experto de código** | `________________` | Ejecuta `audit.py`, completa `checklist-auditoria-codigo`. |
| **Miembro observador** | `________________` *(opcional)* | Sin voto, puede emitir opinión escrita. |

> Un mismo integrante puede ocupar hasta dos roles si el comité es de dos personas,  
> **excepto** Presidente + Secretario (deben ser distintos para independencia de acta).

---

## 5. Quorum y votación

| Criterio | Regla |
|---|---|
| **Quorum mínimo** | Presidente + al menos 1 experto (financiero **o** de código) |
| **Aprobación** | Mayoría simple de presentes con voto |
| **Empate** | Voto de calidad del Presidente |
| **Urgencia** | El Presidente puede emitir dictamen provisional con 1 experto; debe ratificarse en 72 h |

---

## 6. Frecuencia de revisión

| Tipo de revisión | Frecuencia mínima | Condición de convocatoria extraordinaria |
|---|---|---|
| Revisión operativa | Semanal (lunes antes del arranque) | — |
| Revisión de capital | Mensual | Capital disponible cambia > 20% |
| Revisión de código | Ante cada cambio mayor en `demo_trader.py` o `s03_asian_range.py` | Commit que modifique lógica de señales o riesgo |
| Revisión extraordinaria | — | Drawdown diario > 2%, kill switch activado, o incidente de seguridad |

---

## 7. Conflictos de interés

Cualquier miembro con interés directo en el resultado de un dictamen (p. ej. el desarrollador auditando su propio código) debe:

1. Declararlo al inicio de la reunión (consta en acta).
2. Abstenerse de votar en ese punto específico.
3. Quedar registrado en la sección "Conflictos declarados" del acta.

---

## 8. Actualizaciones a este mandato

Este documento se revisa y actualiza cuando:
- Cambia un miembro del comité.
- Se pasa de cuenta Demo a Live.
- El capital gestionado supera un nuevo umbral acordado (p. ej. $10 000).
- Transcurren 6 meses sin actualización.

---

## 9. Firmas de constitución

| Rol | Nombre | Fecha |
|---|---|---|
| Presidente | `________________` | `AAAA-MM-DD` |
| Secretario | `________________` | `AAAA-MM-DD` |
| Experto financiero | `________________` | `AAAA-MM-DD` |
| Experto de código | `________________` | `AAAA-MM-DD` |
