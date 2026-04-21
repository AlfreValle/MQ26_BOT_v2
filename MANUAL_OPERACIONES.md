# MQ26 BOT v2 — Manual de Operaciones Diarias

**Estrategia:** S03 Asian Range v4 (Asian scalp · London BO · NY Open BO)  
**Capital inicial:** $2,000 USD  
**Cuenta:** IC Markets SC-Demo (cambiar a Live al fondear)  
**Intervalo de loop:** cada 5 minutos  

> **Gobernanza:** El marco de auditoría formal (mandato, checklists, dictámenes)  
> se encuentra en [`governance/committee/`](governance/committee/README.md).

---

## INICIO RÁPIDO — Primer Arranque del Día

```bash
cd C:\Users\DELL\OneDrive\Documentos\MQ26_BOT\MQ26_BOT_v2

# 1. Verificar sistema (30 segundos)
python preflight_check.py

# 2. Arrancar el bot
python demo_trader.py --capital 2139

# 3. En otra terminal — abrir el dashboard
streamlit run dashboard.py --server.port 8504```

> El dashboard se abre en: **http://localhost:8504**

---

## HORARIO OPERATIVO

| Hora UTC | Hora Colombia (UTC-5) | Evento |
|----------|----------------------|--------|
| 00:00 – 07:00 | 19:00 – 02:00 | Sesión Asiática — S03 busca rangos |
| 07:00 – 08:30 | 02:00 – 03:30 | **London Open — momento clave del bot** |
| 12:00 – 16:00 | 07:00 – 11:00 | Overlap London/NY — mayor volatilidad |
| 22:00 Vie | 17:00 Vie | Cierre mercado Forex hasta Dom 22:00 UTC |

**BTCUSD y ETHUSD operan 24/7** — el bot los evalúa siempre.

---

## RUTINA DIARIA

### ☀️ MAÑANA (antes de abrir el bot)

1. **Verificar que MT5 está abierto y logueado**
   - Icono MT5 en la barra de tareas → cuenta demo conectada
   - Balance visible en MT5

2. **Revisar Telegram** — ¿llegó el reporte del día anterior?
   - Si el bot corrió ayer, debe haber un mensaje de resumen nocturno

3. **Correr auditoría** (1 vez por semana mínimo, diario los primeros 15 días)
   ```bash
   python audit.py
   python audit.py --export-md   # Markdown para checklist del comité → data/reports/audit_evidence.md
   ```
   - Todos los checks deben ser `[  OK  ]` o `[ WARN ]`
   - Un solo `[ERROR!]` = **NO arrancar el bot**

4. **Verificar noticias de alto impacto del día**
   - El bot tiene M91 (filtro automático), pero es bueno saberlo:
   - Fuente: https://www.forexfactory.com (solo noticias rojas)
   - Noticias clave: NFP (primer viernes del mes), FOMC, CPI, GDP

5. **Arrancar el bot**
   ```bash
   python demo_trader.py --capital 2000
   ```

---

### 🌞 DURANTE EL DÍA (monitoreo)

**Frecuencia recomendada:** revisar cada 2-4 horas

#### En Telegram, esperar estas alertas:
| Mensaje | Qué significa | Acción |
|---------|--------------|--------|
| `SEÑAL DETECTADA` | El bot encontró una oportunidad | Ninguna (automático) |
| `ORDEN EJECUTADA` | Se abrió una posición | Verificar en MT5 |
| `TRADE CERRADO` | La posición se cerró con TP o SL | Revisar resultado |
| `⚠️ DAILY LOSS` | Perdida del día ≥ 2% | Bot pausado, normal |
| `🚨 KILL SWITCH` | DD ≥ 12% — **EMERGENCIA** | Ver sección emergencias |

#### En el Dashboard (http://localhost:8503):
- Tab **Live MT5** → verificar balance, equity, posiciones abiertas
- Tab **Backtest Analysis** → debe mostrar solo S03_AsianRange en verde

#### Señales de alerta en los logs:
```
# Log normal — todo bien:
22:18:42 | INFO | Tick 2026-04-18 22:18:42 UTC
22:18:43 | INFO | Cuenta | Balance=$300.00 | Equity=$301.50 | DD=0.00%

# Log preocupante — revisar:
22:18:42 | WARNING | M73 DAILY LOSS LIMIT activo    ← bot pausó, normal
22:18:42 | WARNING | M91 BLACKOUT: NFP en 20 min    ← filtro noticias activo
22:18:42 | ERROR   | Orden fallida para EURUSD       ← verificar MT5
22:18:42 | CRITICAL| KILL SWITCH: DD=12.5%           ← EMERGENCIA
```

---

### 🌙 NOCHE (cierre del día)

1. **Revisar el reporte diario en Telegram**
   - PnL del día, trades ejecutados, win rate

2. **En el Dashboard** → tab Backtest Analysis → verificar equity curve

3. **¿Dejar el bot corriendo de noche?**
   - **SÍ** para BTCUSD y ETHUSD (24/7, el rango asiático es nocturno)
   - El bot maneja el horario solo — no hay que apagarlo
   - Si querés apagarlo: `Ctrl+C` en la terminal del bot

4. **Si lo apagás**, al día siguiente:
   - Verificar en MT5 que no quedaron posiciones abiertas huérfanas
   - Si hay posiciones abiertas sin bot: cerrar manualmente en MT5

---

## 🚨 PROCEDIMIENTOS DE EMERGENCIA

### Escenario 1: Kill Switch disparado (DD ≥ 12%)

```
Mensaje Telegram: 🚨 KILL SWITCH — DD=12.5% — Equity: $1,750
```

**Pasos:**
1. **NO entrar en pánico** — el bot ya cerró todas las posiciones
2. Abrir MT5 → verificar que no quedan posiciones abiertas
3. Si quedaron posiciones: cerrarlas manualmente en MT5
4. Analizar el log: `data/logs/demo_trader.log`
5. **NO reiniciar el bot el mismo día**
6. Al día siguiente: revisar qué par causó el drawdown
7. Si el problema es sistemático → avisar antes de reiniciar

### Escenario 2: Bot se cayó / Ctrl+C accidental

1. Verificar posiciones abiertas en MT5 (pueden seguir abiertas)
2. Decidir: ¿dejarlas correr o cerrarlas manualmente?
3. Reiniciar el bot:
   ```bash
   python demo_trader.py --capital 2000
   ```
4. El bot retoma de cero — no pierde el historial de trades (quedó en MT5)

### Escenario 3: MT5 se desconectó

```
Log: ERROR | No se pudo conectar a MT5
```

1. Verificar que MT5 está abierto en Windows
2. Verificar conexión a internet
3. En MT5: clic derecho en el símbolo → reconectar
4. Reiniciar el bot después de confirmar conexión

### Escenario 4: Daily Loss Limit activado

```
Log: WARNING | M73 DAILY LOSS LIMIT: pérdida del día 2.1% ≥ 2%
```

**Esto es normal y esperado.** Significa:
- El bot perdió > 2% del capital hoy
- Automáticamente pausa nuevas entradas
- Las posiciones existentes siguen corriendo
- Al día siguiente (reset a medianoche UTC) vuelve a operar normalmente
- **NO apagar ni reiniciar** — el bot está funcionando correctamente

### Escenario 5: Telegram no llegan mensajes

1. Verificar que `TG_ENABLED=true` en `.env`
2. Verificar token: https://api.telegram.org/bot**TU_TOKEN**/getMe
3. Escribirle al bot en Telegram (para activar el chat)
4. El bot sigue operando aunque Telegram falle — son alertas opcionales

---

## SEMANA 1 — Plan de Lanzamiento Demo

| Día | Tarea | Comando |
|-----|-------|---------|
| Día 1 | Auditoría completa | `python audit.py` |
| Día 1 | Primer backtest limpio | `python main_backtest.py --strategy s03` |
| Día 1 | Dashboard funcionando | `streamlit run dashboard.py --server.port 8503` |
| Día 1-3 | Modo dry-run (sin órdenes) | `python demo_trader.py --dry-run --capital 2000` |
| Día 4-7 | Demo real (con órdenes demo) | `python demo_trader.py --capital 2000` |
| Semana 2 | Confirmar primeros trades ejecutados | Revisar Telegram + Dashboard |
| Semana 3 | Evaluar resultados demo | Comparar con backtest |
| Mes 1 | Decisión de ir a live | Solo si demo es rentable |

---

## PASAR A CUENTA REAL (cuando el balance llegue)

### Checklist pre-live:

```
[ ] Cuenta IC Markets fondeada con $2,000 USD
[ ] MT5 conectado con cuenta real (no demo)
[ ] Editar .env con credenciales reales:
      MT5_LOGIN=<numero de cuenta real>
      MT5_PASSWORD=<password real>
      MT5_SERVER=ICMarketsSC-Live01
      MODE=live
[ ] python preflight_check.py  →  TODO OK
[ ] python audit.py            →  0 errores
[ ] python demo_trader.py --capital 2000
```

### Servidores IC Markets (posibles):
- `ICMarketsSC-Live01` ← más común
- `ICMarketsSC-Live02`
- `ICMarketsSC-Live03`

> El número exacto del servidor aparece en el email de bienvenida de IC Markets
> o en: MT5 → Archivo → Abrir cuenta → buscar "IC Markets"

---

## COMANDOS DE REFERENCIA

```bash
# === OPERACION DIARIA ===
python demo_trader.py --capital 2000          # Bot completo (Top 8)
python demo_trader.py --dry-run --capital 2000  # Solo señales, sin órdenes
python demo_trader.py --symbol BTCUSD --capital 2000  # Solo un par

# === VERIFICACION ===
python preflight_check.py        # Check rápido (pre-arranque)
python audit.py                  # Auditoría completa (semanal)
python test_mt5_connection.py    # Solo verificar MT5

# === BACKTEST (para validar cambios) ===
python main_backtest.py --strategy s03 --period 60d    # Top 8, 60 días
python main_backtest.py --strategy s03 --symbol BTCUSD # Un par específico

# === DASHBOARD ===
streamlit run dashboard.py --server.port 8503   # http://localhost:8503

# === LOGS ===
# Ver log en tiempo real (Windows PowerShell):
Get-Content data\logs\demo_trader.log -Wait -Tail 50
```

---

## METRICAS DE SALUD DEL BOT

Después de la primera semana de demo, estos son los números que deberías ver:

| Métrica | Objetivo | Alerta si... |
|---------|----------|-------------|
| Win Rate diario | ≥ 65% | < 50% por 3 días seguidos |
| PF semanal | ≥ 1.5 | < 1.0 en la semana |
| Max DD diario | < 5% | > 8% en un día |
| Trades por día | 2-6 | 0 trades = bot no opera / > 10 = algo mal |
| Duración promedio | 1-3 horas | > 8 horas = revisar SL/TP |

---

## CONTACTO Y SOPORTE

- **Log principal:** `data/logs/demo_trader.log`
- **Reporte HTML:** `data/reports/backtest_report.html`
- **Trades CSV:** `data/reports/backtest_report_trades.csv`
- **Configuración:** `.env` (nunca compartir)
- **Dashboard:** http://localhost:8504

---

*MQ26 BOT v2 — Estrategia S03 Asian Range v3 | IC Markets MT5*  
*Generado: 2026-04-18*
