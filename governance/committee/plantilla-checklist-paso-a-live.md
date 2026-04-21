# Checklist Paso a Live — MQ26 BOT v2

> **Uso:** completar **antes** de poner `MODE=live` y operar cuenta real.  
> Complementa `plantilla-checklist-auditoria-financiera.md` y `plantilla-checklist-auditoria-codigo.md`.  
> No pegar credenciales ni `.env` completo.

---

## Encabezado

| Campo | Valor |
|---|---|
| **Fecha** | `AAAA-MM-DD` |
| **Commit** | `git rev-parse --short HEAD` → `________` |
| **Cuenta destino** | IC Markets …`____` (solo últimos 4 dígitos) |
| **Capital fondeado verificado** | `[ ]` Vista en MT5 + extracto bancario / comprobante de fondeo |
| **Capital mínimo acordado por el comité** | `[ ]` ≥ `$2,000` USD (o monto escrito: `$________`) |

---

## Configuración y arranque

| Ítem | OK |
|---|---|
| `.env`: `MODE=live` | `[ ]` |
| `.env`: `MT5_SERVER` apunta a servidor **Live** (no demo) | `[ ]` |
| `MT5_LOGIN` / `MT5_PASSWORD` probados con `python test_mt5_connection.py` | `[ ]` |
| `python preflight_check.py` → sin errores bloqueantes | `[ ]` |
| `python audit.py` → **0 errores críticos** | `[ ]` |
| `python audit.py --export-md` → evidencia guardada en `data/reports/audit_evidence.md` | `[ ]` |
| `python demo_trader.py --capital ______` alineado con balance real (diff menor que 10%) | `[ ]` |
| AutoTrading en MT5 **habilitado** (toolbar verde) | `[ ]` |

---

## Spreads y entorno real

| Ítem | OK |
|---|---|
| Spreads medidos en Live (BTCUSD, XAUUSD, majors) anotados | `[ ]` |
| Comparación vs demo: diferencia documentada | `[ ]` |
| Slippage esperado y comisiones revisadas con el bróker | `[ ]` |

---

## Riesgo y mandato

| Ítem | OK |
|---|---|
| Drawdown máximo aceptado en Live documentado (`____%`) | `[ ]` |
| Kill switch y daily loss entendidos por operador | `[ ]` |
| `plantilla-mandato-y-composicion.md` firmado / vigente | `[ ]` |
| Dictamen de comité **Aprueba** o **Aprueba con condiciones** para Live | `[ ]` |

---

## Post go-live (primeras 48 h)

| Ítem | OK |
|---|---|
| Primera orden: ticket y hora registrados | `[ ]` |
| Telegram recibe alertas | `[ ]` |
| `data/logs/signal_funnel.json` existe y se actualiza durante la operación | `[ ]` |

---

## Resolución

`[ ] Autorizado pasar a Live` — Firmado: `________________` — Fecha: `____`

`[ ] NO autorizado` — Motivo: `________________`
