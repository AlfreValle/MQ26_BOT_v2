"""
Configuración central del bot — Pydantic v2 con .env support.
Todos los parámetros ajustables sin tocar código.
"""
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "trades.db"


class RiskSettings(BaseSettings):
    """Límites de riesgo globales — 5 capas."""
    model_config = SettingsConfigDict(env_prefix="RISK_", extra="ignore")

    # Capa 1 — Por trade
    risk_per_trade_pct: float = Field(default=1.0, ge=0.1, le=3.0,
        description="Riesgo por trade en % del capital")
    scalping_risk_pct: float = Field(default=0.5, ge=0.1, le=1.0,
        description="Riesgo para scalping (menor)")
    swing_risk_pct: float = Field(default=1.5, ge=0.5, le=2.0,
        description="Riesgo para swing/position trades")
    min_rr_ratio: float = Field(default=1.5,
        description="R:R mínimo para aceptar una señal")

    # Capa 2 — Por sesión
    max_daily_loss_pct: float = Field(default=3.0,
        description="Pérdida máxima diaria en % → stop total del día")
    max_trades_per_session: int = Field(default=6,
        description="Máximo de trades por sesión activa")
    consecutive_losses_pause: int = Field(default=3,
        description="Pausar 2 horas si N pérdidas consecutivas")

    # Capa 3 — Portafolio
    max_open_positions: int = Field(default=3,
        description="Máximo de posiciones abiertas simultáneas")
    max_correlated_exposure: float = Field(default=4.0,
        description="Exposición máxima al USD como base/cotización %")
    correlation_threshold: float = Field(default=0.7,
        description="Si 2 posiciones correlación > X → reducir size 50%")

    # Capa 4 — Drawdown
    dd_defensive_pct: float = Field(default=5.0,
        description="DD% → modo defensivo (size al 50%)")
    dd_scalping_only_pct: float = Field(default=8.0,
        description="DD% → solo scalping con 0.25% riesgo")
    dd_kill_switch_pct: float = Field(default=12.0,
        description="DD% → KILL SWITCH TOTAL")

    # Capa 5 — Calendar
    news_buffer_minutes: int = Field(default=15,
        description="Minutos buffer antes/después de noticias alto impacto")
    fomc_nfp_size_reduction: float = Field(default=0.5,
        description="Reducir tamaño al X% en días FOMC/NFP/CPI")


class BacktestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BT_", extra="ignore")

    initial_capital: float = Field(default=10_000.0,
        description="Capital inicial de backtesting en USD")
    commission_per_lot: float = Field(default=3.5,
        description="Comisión por lote en USD (IC Markets ECN: $3.5)")
    slippage_pips: float = Field(default=0.2,
        description="Slippage estimado en pips")
    # Datos históricos
    forex_period: str = Field(default="2y",
        description="Período de datos para backtesting")
    forex_interval_m5: str = Field(default="5m",
        description="Intervalo M5 para estrategias intradía")
    forex_interval_h1: str = Field(default="1h",
        description="Intervalo H1 para estructura de mercado")
    forex_interval_h4: str = Field(default="1d",
        description="Intervalo H4 (yfinance usa 1d como proxy)")


class MT5Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MT5_", env_file=".env", extra="ignore")

    login: int = Field(default=0, description="Login de cuenta MT5")
    password: str = Field(default="", description="Password de cuenta MT5")
    server: str = Field(default="ICMarketsSC-Demo",
        description="Servidor MT5 de IC Markets demo")
    timeout: int = Field(default=60_000, description="Timeout conexión ms")
    magic_number: int = Field(default=26042026,
        description="Magic number del EA — no cambiar")


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TG_", env_file=".env", extra="ignore")

    token: str = Field(default="", description="Token del bot de Telegram")
    chat_id: str = Field(default="", description="Chat ID para alertas")
    enabled: bool = Field(default=False,
        description="Activar alertas por Telegram")


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # ignorar TG_*, MT5_*, RISK_* leídos por sub-modelos
    )

    # Modo operativo
    mode: str = Field(default="backtest",
        description="'backtest' | 'demo' | 'live'")
    log_level: str = Field(default="INFO")

    # Sub-configuraciones
    risk: RiskSettings = Field(default_factory=RiskSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    mt5: MT5Settings = Field(default_factory=MT5Settings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"backtest", "demo", "live"}
        if v not in allowed:
            raise ValueError(f"mode debe ser uno de {allowed}")
        return v

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"

    @property
    def is_backtest(self) -> bool:
        return self.mode == "backtest"


# Singleton global — importar desde aquí en todo el proyecto
settings = BotSettings()
