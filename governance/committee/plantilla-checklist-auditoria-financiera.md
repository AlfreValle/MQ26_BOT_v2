# Checklist de Auditoría Financiera — MQ26 BOT v2

> **Instrucciones:** Completar por el Experto Financiero en cada ciclo de revisión.  
> Adjuntar como evidencia extractos de MT5 o capturas de pantalla (sin mostrar credenciales).  
> Referencia de cuenta: usar solo los últimos 4 dígitos.

---

## Encabezado

| Campo | Valor |
|---|---|
| **Periodo cubierto** | `AAAA-MM-DD` al `AAAA-MM-DD` |
| **Cuenta** | IC Markets …`____` |
| **Modalidad** | `[ ] Demo` `[ ] Live` |
| **Revisado por** | `________________` |
| **Fecha de revisión** | `AAAA-MM-DD` |

---

## Sección 1 — Conciliación de Balance y Equity

| Control | Esperado / Referencia | Valor observado | Estado |
|---|---|---|---|
| Balance MT5 al inicio del periodo | `$________________` | `$________________` | `[ ] OK` `[ ] Desvío` |
| Equity MT5 al cierre del periodo | `$________________` | `$________________` | `[ ] OK` `[ ] Desvío` |
| Diferencia balance vs equity (posiciones abiertas) | Debe ser explicable por P&L flotante | `$________________` | `[ ] OK` `[ ] Revisar` |
| Capital de referencia declarado al arranque (`--capital`) | Debe ser cercano al balance real (< 10% de diferencia) | `$________________` | `[ ] OK` `[ ] WARN: diferencia > 10%` |
| Coincidencia con log de arranque del bot | Revisar `data/logs/demo_trader.log`: línea `"Portfolio inicializado desde MT5"` | `$________________` | `[ ] OK` `[ ] No encontrado` |

**Observaciones:**
```
________________
```

---

## Sección 2 — Métricas de tendencia (últimos 4 dictámenes)

> Rellenar desde dictámenes o checklists financieros previos. Detecta deterioro silencioso.

| Periodo (fin) | Win rate | DD máx % | P&L acum. USD |
|---|---|---|---|
| T-3 | `____%` | `____` | `+/-____` |
| T-2 | `____%` | `____` | `+/-____` |
| T-1 | `____%` | `____` | `+/-____` |
| **Actual (T0)** | `____%` | `____` | `+/-____` |

| Delta | T-1 → T0 | Evaluación |
|---|---|---|
| **Δ Win rate** | `____` pp | `[ ] estable` `[ ] mejora` `[ ] deterioro` |
| **Δ Drawdown máx** | `____` pp | `[ ] estable` `[ ] mejor` `[ ] peor` |
| **Δ P&L acumulado** | `$____` | `[ ] estable` `[ ] mejor` `[ ] peor` |

---

## Sección 3 — P&L del Periodo

| Métrica | Valor | Evaluación |
|---|---|---|
| P&L total del periodo (USD) | `+/- $________________` | `[ ] Positivo` `[ ] Negativo` `[ ] Breakeven` |
| P&L como % del balance inicial | `+/- ____%` | `[ ] Dentro de expectativa` `[ ] Revisar` |
| Número de trades cerrados | `____` | — |
| Win rate del periodo | `____%` | Referencia S03: WR ≥ 65% en 30 días |
| Profit Factor del periodo | `____` | Referencia S03: PF > 1.0 |
| Trade de mayor ganancia | `+$________________ (símbolo: ____)` | — |
| Trade de mayor pérdida | `-$________________ (símbolo: ____)` | — |

**Evidencia** (pegar extracto de `data/logs/` o resumen del journal — sin contraseñas):
```
________________
```

---

## Sección 4 — Control de Drawdown

| Control | Límite configurado | Valor observado | Estado |
|---|---|---|---|
| Drawdown diario máximo del periodo | 3.0% (kill switch) | `____%` | `[ ] OK` `[ ] WARN` `[ ] ERROR` |
| Drawdown semanal máximo | Política interna: `____%` | `____%` | `[ ] OK` `[ ] WARN` |
| ¿Se activó el kill switch en el periodo? | No debería activarse | `[ ] Sí` `[ ] No` | `[ ] OK` `[ ] Revisar causa` |
| ¿Se activó daily loss limit (nivel 2%)? | Posible, con pausa | `[ ] Sí (____x)` `[ ] No` | `[ ] OK` `[ ] Documentar` |
| Equity máximo alcanzado (peak) | — | `$________________` | — |
| Equity mínimo alcanzado (valley) | — | `$________________` | — |

**Observaciones sobre drawdown:**
```
________________
```

---

## Sección 5 — Demo vs Live

> Completar solo si la cuenta es Live o se está evaluando el paso.

| Control | Estado |
|---|---|
| ¿Se operó en cuenta real en este periodo? | `[ ] Sí` `[ ] No (solo demo)` |
| Si Live: ¿los resultados son consistentes con el backtest y la demo? | `[ ] Sí` `[ ] No — detalle: ________________` |
| ¿Se requiere aprobación del comité para continuar en Live? | `[ ] Sí` `[ ] No` |
| Diferencia de spreads demo vs live (si se mide) | `________________` | 

---

## Sección 6 — Revisión de Costos (Fees y Spread)

| Control | Referencia | Valor observado | Estado |
|---|---|---|---|
| Spread máximo tolerado BTCUSD | 200 pips (config) | `____` pips promedio | `[ ] OK` `[ ] Excedido` |
| Spread máximo tolerado XAUUSD | 50 pips (config) | `____` pips promedio | `[ ] OK` `[ ] Excedido` |
| Spread máximo tolerado AUDUSD/NZDUSD | 3–4 pips (config) | `____` pips promedio | `[ ] OK` `[ ] Excedido` |
| Comisión por roundtrip (si aplica) | Según bróker | `$________________ / lot` | `[ ] Dentro de expectativa` |
| ¿Los spreads altos rechazaron señales válidas? | Ver `demo_trader.log`: `"spread demasiado alto"` | `____` ocurrencias | `[ ] Aceptable` `[ ] Revisar umbral` |

---

## Sección 7 — Muestra de Operaciones del Periodo

> Seleccionar al menos 3 operaciones: 1 ganadora, 1 perdedora, 1 reciente.  
> Fuente: `data/logs/demo_trader.log` o `data/trade_journal.json` (si existe).

| # | Símbolo | Dirección | Entrada | SL | TP cerrado | P&L (USD) | Sesión | Observación |
|---|---|---|---|---|---|---|---|---|
| 1 | `____` | `BUY/SELL` | `____` | `____` | `TP1/TP2/SL` | `+/-$____` | `Asian/London/NY` | `________________` |
| 2 | `____` | `BUY/SELL` | `____` | `____` | `TP1/TP2/SL` | `+/-$____` | `Asian/London/NY` | `________________` |
| 3 | `____` | `BUY/SELL` | `____` | `____` | `TP1/TP2/SL` | `+/-$____` | `Asian/London/NY` | `________________` |

**¿Los trades revisados respetan la política de riesgo (SL siempre presente, lot coherente con 1% del capital)?**
`[ ] Sí` `[ ] No — detalle: ________________`

---

## Sección 8 — Alertas Telegram del Periodo

| Control | Estado |
|---|---|
| ¿Se recibieron alertas de señal detectada? | `[ ] Sí` `[ ] No` |
| ¿Se recibieron alertas de orden ejecutada? | `[ ] Sí` `[ ] No` |
| ¿Se recibieron alertas de kill switch? | `[ ] Sí (cuántas: ____)` `[ ] No` |
| ¿Se recibieron heartbeats cada 6 horas? | `[ ] Sí` `[ ] No — posible interrupción` |
| Última alerta recibida | `AAAA-MM-DD HH:MM` | 

---

## Sección 9 — Política Interna de Riesgo

> Completar según los límites acordados internamente (pueden diferir de los del bot).

| Límite | Política interna | ¿Se respetó? |
|---|---|---|
| Riesgo máximo por trade | `____%` del capital | `[ ] Sí` `[ ] No` |
| Máximo de posiciones simultáneas | `____` | `[ ] Sí` `[ ] No` |
| Drawdown semanal máximo tolerado | `____%` | `[ ] Sí` `[ ] No` |
| Símbolos permitidos | `BTCUSD, XAUUSD, AUDUSD, NZDUSD, ETHUSD, GBPUSD, EURUSD, AUDJPY` | `[ ] Sí` `[ ] No` |
| Operación en fin de semana | Solo crypto | `[ ] Sí` `[ ] No` |

---

## Sección 10 — Funnel de señales (KPI de calidad)

> Fuente recomendada: `data/logs/signal_funnel.json` (actualizado al final de cada tick del bot).  
> Si el archivo no existe, el bot no ha corrido aún en esta máquina — dejar en blanco y anotar.

| Métrica (periodo) | Valor |
|---|---|
| Señales generadas (suma `generated`) | `____` |
| Filtradas por spread (`filtered_spread`) | `____` |
| Filtradas por staleness #51 (`filtered_staleness`) | `____` |
| Filtradas por session guard #86 (`filtered_session`) | `____` |
| Ejecutadas (`executed`) | `____` |
| **Ratio ejecutadas / generadas** | `____` (ej. `0.35` = 35%) |

**Umbral de alerta:** si `generadas > 0` y el ratio es **menor que 0,30 (30%)** → revisar filtros, spreads o configuración.

`[ ] Ratio OK` `[ ] Ratio bajo — investigar` `[ ] Sin datos (bot no operó)`

---

## Resultado de esta sección

`[ ] Sin hallazgos` `[ ] Hallazgos menores (WARN)` `[ ] Hallazgos críticos (ERROR)`

**Hallazgos para acta:**
```
________________
```

---

*Firma del Experto Financiero:* `________________` — `AAAA-MM-DD`
