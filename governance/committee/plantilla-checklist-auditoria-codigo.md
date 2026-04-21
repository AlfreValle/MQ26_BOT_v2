# Checklist de Auditoría de Código — MQ26 BOT v2

> **Instrucciones:** Ejecutar `python audit.py` y pegar la salida en cada sección, **o** generar Markdown con:  
> `python audit.py --export-md` → archivo por defecto `data/reports/audit_evidence.md` (o `python audit.py --export-md -` para stdout).  
> Esta checklist mapea 1:1 las **10 capas** del docstring de `audit.py` (líneas 4–14).  
> No incluir tokens, contraseñas ni rutas absolutas con nombres de usuario.

---

## Encabezado

| Campo | Valor |
|---|---|
| **Periodo cubierto** | `AAAA-MM-DD` al `AAAA-MM-DD` |
| **Commit de código auditado** | `git rev-parse --short HEAD` → `________` |
| **Rama** | `git branch --show-current` → `________` |
| **Ejecutado por** | `________________` |
| **Fecha de ejecución** | `AAAA-MM-DD HH:MM UTC` |
| **Python** | `python --version` → `________` |

**Salida completa de `python audit.py`:**
```
[PEGAR AQUÍ — sin tokens ni credenciales]
```

**Resumen de errores / advertencias:**
- `[ERROR!]` críticos: `____`
- `[ WARN ]` advertencias: `____`

---

## Capa 1 — Configuración y parámetros de riesgo

> `audit.py` sección 1: verifica `.env`, `settings.py`, parámetros de riesgo cargados.

| Ítem | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|
| Archivo `.env` presente y legible | `[OK/WARN/ERROR]` | — | `[ ]` |
| `TG_TOKEN` cargado (sin mostrarlo) | `[OK/WARN/ERROR]` | Solo verificar que existe, no pegar valor | `[ ]` |
| `TG_CHAT_ID` cargado | `[OK/WARN/ERROR]` | — | `[ ]` |
| `DAILY_LOSS_LIMIT` = 2.0% | `[OK/WARN/ERROR]` | Confirmar en `demo_trader.py` línea `DAILY_LOSS_LIMIT` | `[ ]` |
| `DAILY_LOSS_STOP` = 3.0% | `[OK/WARN/ERROR]` | — | `[ ]` |
| `MAX_OPEN_POSITIONS` = 3 | `[OK/WARN/ERROR]` | — | `[ ]` |
| `LOOP_INTERVAL_SEC` = 300 | `[OK/WARN/ERROR]` | — | `[ ]` |

**Evidencia (fragmento de salida de audit.py para esta sección):**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 2 — Integridad de la estrategia S03

> `audit.py` sección 2: verifica que `AsianRangeStrategy` importa, instancia y tiene atributos clave.

| Ítem | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|
| `AsianRangeStrategy` importa sin error | `[OK/WARN/ERROR]` | `python -c "from strategies.forex.s03_asian_range import AsianRangeStrategy"` | `[ ]` |
| Atributo `min_range_pips` presente | `[OK/WARN/ERROR]` | — | `[ ]` |
| Atributo `use_adx_filter = True` | `[OK/WARN/ERROR]` | — | `[ ]` |
| Atributo `use_di_filter = True` (#80) | `[OK/WARN/ERROR]` | Confirmar en código fuente | `[ ]` |
| `adx_breakout_min = 20.0` (#77) | `[OK/WARN/ERROR]` | — | `[ ]` |
| Método `_breakout_ny_open` presente (#95) | Manual | `grep -n "_breakout_ny_open" strategies/forex/s03_asian_range.py` | `[ ]` |
| Modo 3 NY Open en `_process_day()` | Manual | `grep -n "MODO 3" strategies/forex/s03_asian_range.py` | `[ ]` |
| `generate_signals()` retorna lista | `[OK/WARN/ERROR]` | — | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 3 — Conexión MT5 y estado de cuenta

> `audit.py` sección 3: verifica inicialización MT5, símbolo activo, cuenta.

| Ítem | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|
| MT5 inicializa sin error | `[OK/WARN/ERROR]` | MT5 debe estar abierto con login activo | `[ ]` |
| Cuenta conectada (últimos 4 dígitos) | `[OK/WARN/ERROR]` | Confirmar `…____` | `[ ]` |
| Balance reportado por MT5 | `[OK/WARN/ERROR]` | Valor: `$________________` | `[ ]` |
| Al menos 1 símbolo del portafolio activo | `[OK/WARN/ERROR]` | — | `[ ]` |
| Tick obtenible para BTCUSD | `[OK/WARN/ERROR]` | — | `[ ]` |
| Tick obtenible para XAUUSD | `[OK/WARN/ERROR]` | — | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 4 — Datos de backtest (CSV)

> `audit.py` sección 4: verifica CSV de resultados S03, todos con PF > 1.

| Ítem | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|
| Archivo CSV de backtest presente | `[OK/WARN/ERROR]` | Ruta: `data/backtest_*.csv` | `[ ]` |
| Todos los símbolos con PF > 1.0 | `[OK/WARN/ERROR]` | Ver columna `profit_factor` | `[ ]` |
| Símbolos excluidos ausentes (USDCAD, AUDNZD…) | `[OK/WARN/ERROR]` | — | `[ ]` |
| Sharpe ratio del portafolio ≥ 8.0 | `[OK/WARN/ERROR]` | Ver resumen CSV | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 5 — Protecciones de riesgo activas

> `audit.py` sección 5: verifica M72 correlación, M73 daily loss, M77 max pos, M91 PID lock, M136 priority.

| Protección | Descripción | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|---|
| **M72** Correlación AUDUSD/NZDUSD | Size reducido a 60% cuando ambas activas | `[OK/WARN/ERROR]` | `grep "corr_reduction" demo_trader.py` | `[ ]` |
| **M73/#76** Daily loss tiered | 1.5% WARN / 2% PAUSE / 3% STOP | `[OK/WARN/ERROR]` | Constantes `DAILY_LOSS_*` en código | `[ ]` |
| **M77** Max posiciones | `MAX_OPEN_POSITIONS = 3` | `[OK/WARN/ERROR]` | Confirmar valor | `[ ]` |
| **M91/#91** PID lock | Un proceso simultáneo máximo | `[OK/WARN/ERROR]` | `_acquire_pid_lock` en código | `[ ]` |
| PID lock Windows-compatible | Usa `tasklist` vía `_pid_still_running` | **Bloqueante en Windows** | `grep "tasklist" demo_trader.py` | `[ ]` |
| **M136** Signal priority | Señales ordenadas por Sharpe | `[OK/WARN/ERROR]` | `SHARPE_RANK` en código | `[ ]` |
| **#83** SL Recovery on restart | Posiciones sin SL reciben uno al arrancar | Manual | `_recover_missing_sl` en código | `[ ]` |
| **#84** Win scaling (máx ×2.0) | Escala hasta 2× tras 6 wins consecutivos | Manual | `min(2.0, ...)` en `_evaluate_symbol` | `[ ]` |
| **#86** Session guard | Evalúa solo 23:00–14:59 UTC para FX | Manual | `hour_utc < 15` en código | `[ ]` |
| **#88** Anti-tilt cooldown | 1h pausa tras 2 pérdidas en 2h | Manual | `_tilt_cooldown_until` en código | `[ ]` |
| **#90** Weekly scale-down | Size al 50% si semana < -3% | Manual | `_weekly_scale` en código | `[ ]` |
| **#94** Pyramiding | Add 50% lot en ganadores TP1→TP2 | Manual | `pyramid_done` en `_manage_positions` | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 6 — Telegram y alertas

> `audit.py` sección 6: verifica `TelegramAlerter`, token, envío de prueba.

| Ítem | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|
| `TelegramAlerter` importa | `[OK/WARN/ERROR]` | — | `[ ]` |
| Token y chat_id cargados (sin mostrarlos) | `[OK/WARN/ERROR]` | Confirmar que no son vacíos | `[ ]` |
| Envío de mensaje de prueba exitoso | `[OK/WARN/ERROR]` | Verificar recepción en el chat | `[ ]` |
| Alertas `signal_detected`, `order_executed`, `trade_closed` implementadas | `[OK/WARN/ERROR]` | — | `[ ]` |
| Heartbeat cada 6h configurado (`#47`) | Manual | `_last_heartbeat` en código | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 7 — Sistema de archivos y logs

> `audit.py` sección 7: verifica existencia de archivos de log, estado, tamaño.

| Ítem | Estado en `audit.py` | Verificación manual | OK |
|---|---|---|---|
| `data/logs/demo_trader.log` existe | `[OK/WARN/ERROR]` | Tamaño: `____` KB | `[ ]` |
| `data/logs/watchdog.log` existe | `[OK/WARN/ERROR]` | — | `[ ]` |
| `data/logs/bot_state.json` existe | `[OK/WARN/ERROR]` | — | `[ ]` |
| `data/logs/watchdog.json` existe | `[OK/WARN/ERROR]` | Status: `running/stopped` | `[ ]` |
| Log no tiene errores críticos recientes (últimas 24h) | Manual | `grep "ERROR" data/logs/demo_trader.log \| tail -20` | `[ ]` |
| `bot_state.json`: formato sig_key correcto (`SYMBOL_YYYYMMDD_DIRECTION`) | Manual | Ver contenido (sin credenciales) | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 8 — Dependencias Python

> `audit.py` sección 8: verifica importación de paquetes requeridos.

| Paquete | Estado en `audit.py` | Versión | OK |
|---|---|---|---|
| `MetaTrader5` | `[OK/WARN/ERROR]` | `________________` | `[ ]` |
| `pandas` | `[OK/WARN/ERROR]` | `________________` | `[ ]` |
| `pandas_ta` | `[OK/WARN/ERROR]` | `________________` | `[ ]` |
| `python-dotenv` | `[OK/WARN/ERROR]` | `________________` | `[ ]` |
| `requests` (o `urllib`) | `[OK/WARN/ERROR]` | `________________` | `[ ]` |
| Todas las dependencias de `requirements.txt` | `[OK/WARN/ERROR]` | — | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 9 — Consistencia de capital

> `audit.py` sección 9: verifica coherencia entre `--capital`, balance MT5 y equity.

| Ítem | Estado en `audit.py` | Valor observado | OK |
|---|---|---|---|
| `--capital` ≈ balance MT5 (diferencia < 10%) | `[OK/WARN/ERROR]` | `$____` vs `$____` (diff `____%`) | `[ ]` |
| Risk per trade ≈ 1% del `--capital` | `[OK/WARN/ERROR]` | `$________________` por trade | `[ ]` |
| Lot mínimo respetado para todos los símbolos | `[OK/WARN/ERROR]` | — | `[ ]` |
| `PortfolioState` inicializado desde MT5 real | Manual | Revisar log línea `"Portfolio inicializado desde MT5"` | `[ ]` |

**Evidencia:**
```
________________
```

**Observaciones:**
```
________________
```

---

## Capa 10 — Resumen ejecutivo de `audit.py`

> `audit.py` sección 10: veredicto global del sistema.

| Ítem | Valor |
|---|---|
| **Total checks ejecutados** | `____` |
| **Checks OK** | `____` |
| **Warnings** | `____` |
| **Errores críticos** | `____` |
| **Veredicto de `audit.py`** | `[ ] SISTEMA LISTO` `[ ] REVISAR ADVERTENCIAS` `[ ] SISTEMA CON ERRORES` |

**Líneas del resumen (pegar bloque final de audit.py):**
```
________________
```

---

## Resultado consolidado de esta checklist

> **Regla Capa 5 (Windows):** si el ítem «PID lock Windows-compatible» o el check homónimo de `audit.py` falla → marcar **ERROR** en Capa 5 y **no** marcar aprobación plena hasta corregir.

| Categoría | Sin hallazgos | WARN | ERROR |
|---|---|---|---|
| Capa 1 — Configuración | `[ ]` | `[ ]` | `[ ]` |
| Capa 2 — Estrategia S03 | `[ ]` | `[ ]` | `[ ]` |
| Capa 3 — MT5 | `[ ]` | `[ ]` | `[ ]` |
| Capa 4 — Backtest | `[ ]` | `[ ]` | `[ ]` |
| Capa 5 — Protecciones | `[ ]` | `[ ]` | `[ ]` |
| Capa 6 — Telegram | `[ ]` | `[ ]` | `[ ]` |
| Capa 7 — Logs | `[ ]` | `[ ]` | `[ ]` |
| Capa 8 — Dependencias | `[ ]` | `[ ]` | `[ ]` |
| Capa 9 — Capital | `[ ]` | `[ ]` | `[ ]` |
| Capa 10 — Resumen | `[ ]` | `[ ]` | `[ ]` |

**Hallazgos para acta:**
```
________________
```

---

*Firma del Experto de Código:* `________________` — `AAAA-MM-DD`
