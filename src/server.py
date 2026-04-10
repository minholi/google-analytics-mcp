"""
Google Analytics MCP Server
Servidor MCP para integração com a Google Analytics 4 Data API.
Suporta transporte stdio (local) e HTTP (remoto/equipe).
"""

import json
import logging
import os
import sys
from datetime import date, timedelta
from enum import Enum
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .auth import GoogleAnalyticsAuth
from .client import GoogleAnalyticsClient
from .formatters import (
    format_audience,
    format_conversions,
    format_events,
    format_geographic_performance,
    format_overview,
    format_realtime,
    format_top_pages,
    format_traffic_sources,
)

# ---------------------------------------------------------------------------
# Logging — usa stderr para não poluir o canal stdio do MCP
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("google_analytics_mcp")

# ---------------------------------------------------------------------------
# Servidor MCP
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "google_analytics_mcp",
    instructions=(
        "Servidor MCP para o Google Analytics 4. "
        "Use as ferramentas para analisar tráfego, fontes de aquisição, páginas mais visitadas, "
        "performance geográfica, audiência por dispositivo/browser, eventos, conversões e "
        "dados em tempo real. "
        "Todos os dados vêm diretamente da GA4 Data API em tempo real. "
        "Datas devem estar no formato YYYY-MM-DD. "
        "O property_id padrão é lido de GOOGLE_ANALYTICS_PROPERTY_ID (pode ser sobrescrito por ferramenta)."
    ),
)

# ---------------------------------------------------------------------------
# Enums e constantes
# ---------------------------------------------------------------------------

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class DateRange(str, Enum):
    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


class TrafficGroupBy(str, Enum):
    CHANNEL = "channel"
    SOURCE_MEDIUM = "source_medium"
    CAMPAIGN = "campaign"


class GeoGranularity(str, Enum):
    COUNTRY = "country"
    REGION = "region"
    CITY = "city"


class AudienceBreakdown(str, Enum):
    DEVICE = "deviceCategory"
    BROWSER = "browser"
    OS = "operatingSystem"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client(property_id: Optional[str] = None) -> GoogleAnalyticsClient:
    """Cria cliente autenticado. Lança ValueError com mensagem clara se faltar credencial."""
    auth = GoogleAnalyticsAuth.from_env()
    pid = property_id or os.environ.get("GOOGLE_ANALYTICS_PROPERTY_ID", "")
    if not pid:
        raise ValueError(
            "property_id não informado e GOOGLE_ANALYTICS_PROPERTY_ID não está definido. "
            "Passe property_id no parâmetro ou defina a variável de ambiente."
        )
    return GoogleAnalyticsClient(auth=auth, property_id=pid)


def _resolve_dates(date_range: DateRange, start_date: Optional[str], end_date: Optional[str]) -> tuple[str, str]:
    """Resolve o período em datas absolutas YYYY-MM-DD."""
    today = date.today()
    match date_range:
        case DateRange.LAST_7_DAYS:
            return str(today - timedelta(days=7)), str(today - timedelta(days=1))
        case DateRange.LAST_14_DAYS:
            return str(today - timedelta(days=14)), str(today - timedelta(days=1))
        case DateRange.LAST_30_DAYS:
            return str(today - timedelta(days=30)), str(today - timedelta(days=1))
        case DateRange.THIS_MONTH:
            return str(today.replace(day=1)), str(today)
        case DateRange.LAST_MONTH:
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            return str(last_prev.replace(day=1)), str(last_prev)
        case DateRange.CUSTOM:
            if not start_date or not end_date:
                raise ValueError("Para date_range='custom', forneça start_date e end_date no formato YYYY-MM-DD.")
            return start_date, end_date
    return str(today - timedelta(days=7)), str(today - timedelta(days=1))


def _safe_run(fn, *args, **kwargs) -> str:
    """Wrapper que captura exceções e retorna mensagem amigável."""
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        return f"❌ Erro de configuração: {e}"
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            return "❌ Autenticação falhou. Verifique GOOGLE_ANALYTICS_REFRESH_TOKEN e GOOGLE_ANALYTICS_CLIENT_SECRET."
        if code == 403:
            return "❌ Sem permissão. Verifique se a conta tem acesso à propriedade GA4 informada."
        if code == 429:
            return "❌ Rate limit atingido. Aguarde alguns instantes e tente novamente."
        return f"❌ Erro HTTP {code} ao chamar a GA4 Data API: {e.response.text[:300]}"
    except httpx.TimeoutException:
        return "❌ Timeout na chamada à API. Tente reduzir o período ou o número de métricas."
    except Exception as e:
        logger.exception("Erro inesperado")
        return f"❌ Erro inesperado: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class OverviewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4 (ex: 123456789). "
                    "Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID do ambiente.",
    )
    date_range: DateRange = Field(
        default=DateRange.LAST_7_DAYS,
        description="Período: last_7_days (padrão), last_14_days, last_30_days, "
                    "this_month, last_month ou custom.",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Data inicial para date_range='custom'. Formato: YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Data final para date_range='custom'. Formato: YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    compare_previous: bool = Field(
        default=False,
        description="Se True, inclui comparação com o período anterior de mesmo tamanho.",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="'markdown' para leitura humana (padrão) ou 'json' para dados estruturados.",
    )


class TrafficSourcesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    group_by: TrafficGroupBy = Field(
        default=TrafficGroupBy.CHANNEL,
        description="Agrupamento: 'channel' (padrão), 'source_medium' ou 'campaign'.",
    )
    limit: int = Field(default=25, ge=1, le=100, description="Máximo de linhas a retornar (1–100).")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class TopPagesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    limit: int = Field(default=25, ge=1, le=100)
    page_path_filter: Optional[str] = Field(
        default=None,
        description="Filtrar páginas cujo caminho começa com este prefixo (ex: '/blog', '/produtos').",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class GeographicPerformanceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_30_DAYS)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    granularity: GeoGranularity = Field(
        default=GeoGranularity.COUNTRY,
        description="Nível geográfico: 'country' (padrão), 'region' ou 'city'.",
    )
    limit: int = Field(default=25, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class AudienceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    breakdown: AudienceBreakdown = Field(
        default=AudienceBreakdown.DEVICE,
        description="Dimensão: 'deviceCategory' (padrão), 'browser' ou 'operatingSystem'.",
    )
    limit: int = Field(default=25, ge=1, le=100)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class EventsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_7_DAYS)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    event_names: Optional[list[str]] = Field(
        default=None,
        description="Filtrar apenas estes eventos (ex: ['purchase', 'sign_up']). Se None, retorna todos.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ConversionsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    date_range: DateRange = Field(default=DateRange.LAST_30_DAYS)
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    limit: int = Field(default=50, ge=1, le=200)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class RealtimeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    property_id: Optional[str] = Field(
        default=None,
        description="ID numérico da propriedade GA4. Se omitido, usa GOOGLE_ANALYTICS_PROPERTY_ID.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ---------------------------------------------------------------------------
# Ferramentas MCP
# ---------------------------------------------------------------------------

@mcp.tool(
    name="google_analytics_get_overview",
    annotations={
        "title": "Visão Geral Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_overview(params: OverviewInput) -> str:
    """Retorna os KPIs principais da propriedade GA4 para o período selecionado.

    Métricas: sessões, usuários ativos, novos usuários, pageviews, bounce rate,
    duração média de sessão, taxa de engajamento e conversões.
    Com compare_previous=True, inclui comparação percentual com o período anterior.

    Args:
        params (OverviewInput): property_id, período, compare_previous, formato.

    Returns:
        str: KPIs em formato markdown (padrão) ou JSON estruturado.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_overview(
            start_date=start,
            end_date=end,
            compare_previous=params.compare_previous,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_overview(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_traffic_sources",
    annotations={
        "title": "Fontes de Tráfego Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_traffic_sources(params: TrafficSourcesInput) -> str:
    """Retorna a aquisição de tráfego agrupada por canal, fonte/mídia ou campanha.

    Métricas por origem: sessões, usuários, novos usuários, bounce rate,
    taxa de engajamento e conversões.

    Args:
        params (TrafficSourcesInput): property_id, período, group_by (channel/source_medium/campaign),
            limite e formato.

    Returns:
        str: Tabela de fontes de tráfego em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_traffic_sources(
            start_date=start,
            end_date=end,
            group_by=params.group_by.value,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_traffic_sources(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_top_pages",
    annotations={
        "title": "Top Páginas Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_top_pages(params: TopPagesInput) -> str:
    """Lista as páginas mais visitadas com métricas de engajamento.

    Retorna pageviews, sessões, usuários ativos, bounce rate e duração média
    de sessão por página. Suporta filtro por prefixo de caminho.

    Args:
        params (TopPagesInput): property_id, período, limite, page_path_filter e formato.

    Returns:
        str: Tabela de páginas ordenadas por pageviews em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_top_pages(
            start_date=start,
            end_date=end,
            limit=params.limit,
            page_path_filter=params.page_path_filter,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_top_pages(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_geographic_performance",
    annotations={
        "title": "Performance Geográfica Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_geographic_performance(params: GeographicPerformanceInput) -> str:
    """Retorna performance por localidade geográfica (país, região ou cidade).

    Métricas: sessões, usuários ativos, novos usuários, conversões e bounce rate.
    Destaca a localidade com mais conversões e a com mais sessões sem conversão.

    Args:
        params (GeographicPerformanceInput): property_id, período, granularity
            (country/region/city), limite e formato.

    Returns:
        str: Tabela geográfica com métricas e destaques em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_geographic_performance(
            start_date=start,
            end_date=end,
            granularity=params.granularity.value,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_geographic_performance(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_audience",
    annotations={
        "title": "Audiência Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_audience(params: AudienceInput) -> str:
    """Retorna breakdown da audiência por dispositivo, navegador ou sistema operacional.

    Métricas: sessões, usuários ativos, pageviews, bounce rate e engajamento.

    Args:
        params (AudienceInput): property_id, período, breakdown
            (deviceCategory/browser/operatingSystem), limite e formato.

    Returns:
        str: Tabela de audiência em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_audience(
            start_date=start,
            end_date=end,
            breakdown=params.breakdown.value,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_audience(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_events",
    annotations={
        "title": "Eventos Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_events(params: EventsInput) -> str:
    """Lista os eventos mais disparados na propriedade GA4.

    Retorna nome do evento, contagem total, contagem por usuário e total de usuários.
    Com event_names, filtra apenas os eventos especificados.

    Args:
        params (EventsInput): property_id, período, event_names (filtro opcional),
            limite e formato.

    Returns:
        str: Tabela de eventos ordenados por contagem em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_events(
            start_date=start,
            end_date=end,
            event_names=params.event_names,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_events(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_conversions",
    annotations={
        "title": "Conversões Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def google_analytics_get_conversions(params: ConversionsInput) -> str:
    """Retorna dados de conversão e receita por canal e evento de conversão.

    Apenas eventos marcados como conversão no GA4 aparecem aqui.
    Inclui totais de conversões e receita.

    Args:
        params (ConversionsInput): property_id, período, limite e formato.

    Returns:
        str: Tabela de conversões com receita em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        start, end = _resolve_dates(params.date_range, params.start_date, params.end_date)
        data = client.get_conversions(
            start_date=start,
            end_date=end,
            limit=params.limit,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_conversions(data, start, end)

    return _safe_run(_run)


@mcp.tool(
    name="google_analytics_get_realtime",
    annotations={
        "title": "Dados em Tempo Real Google Analytics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def google_analytics_get_realtime(params: RealtimeInput) -> str:
    """Retorna dados de usuários ativos no momento (últimos 30 minutos).

    Mostra total de usuários ativos e breakdown por página, fonte, país e dispositivo.
    Não suporta date_range — sempre reflete o estado atual.

    Args:
        params (RealtimeInput): property_id e formato.

    Returns:
        str: Usuários ativos e breakdowns em markdown ou JSON.
    """
    def _run():
        client = _get_client(params.property_id)
        data = client.get_realtime()
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return format_realtime(data)

    return _safe_run(_run)
