"""
Formatadores de saída em Markdown para as ferramentas do Google Analytics MCP.
Toda lógica de apresentação fica aqui — separada do cliente de API.
"""

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------

def _fmt_pct(value: float, decimals: int = 2) -> str:
    """GA4 retorna taxas como 0.0–1.0, convertemos para percentual."""
    return f"{value * 100:.{decimals}f}%"


def _fmt_duration(seconds: float) -> str:
    """Converte segundos para string mm:ss."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _fmt_delta(value: Optional[float]) -> str:
    if value is None:
        return "—"
    arrow = "▲" if value >= 0 else "▼"
    return f"{arrow} {abs(value):.1f}%"


def _pct_delta(current: float, previous: float) -> Optional[float]:
    """Calcula variação percentual entre dois valores."""
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def _engagement_emoji(rate: float) -> str:
    """🟢 ≥60%, 🟡 ≥40%, 🔴 <40%"""
    pct = rate * 100
    if pct >= 60:
        return "🟢"
    if pct >= 40:
        return "🟡"
    return "🔴"


def _bounce_emoji(rate: float) -> str:
    """🟢 ≤40%, 🟡 ≤60%, 🔴 >60%"""
    pct = rate * 100
    if pct <= 40:
        return "🟢"
    if pct <= 60:
        return "🟡"
    return "🔴"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def format_overview(data: dict[str, Any], start: str, end: str) -> str:
    curr = data.get("current", {})
    prev = data.get("previous")
    prev_period = data.get("previous_period", {})

    lines = [f"## 📊 Visão Geral Google Analytics — {start} a {end}", ""]

    if not curr:
        lines.append("_Sem dados para o período informado._")
        return "\n".join(lines)

    if prev:
        comp_label = f"{prev_period.get('start')} a {prev_period.get('end')}"
        lines += [
            f"### KPIs Principais _(vs {comp_label})_",
            "",
            "| Métrica | Valor Atual | vs Anterior |",
            "|---------|-------------|-------------|",
        ]
        kpi_rows = [
            ("Sessões", f"{curr.get('sessions', 0):,}", _fmt_delta(_pct_delta(curr.get("sessions", 0), prev.get("sessions", 0)))),
            ("Usuários Ativos", f"{curr.get('activeUsers', 0):,}", _fmt_delta(_pct_delta(curr.get("activeUsers", 0), prev.get("activeUsers", 0)))),
            ("Novos Usuários", f"{curr.get('newUsers', 0):,}", _fmt_delta(_pct_delta(curr.get("newUsers", 0), prev.get("newUsers", 0)))),
            ("Pageviews", f"{curr.get('screenPageViews', 0):,}", _fmt_delta(_pct_delta(curr.get("screenPageViews", 0), prev.get("screenPageViews", 0)))),
            ("Bounce Rate", f"{_bounce_emoji(curr.get('bounceRate', 0))} {_fmt_pct(curr.get('bounceRate', 0))}", _fmt_delta(_pct_delta(curr.get("bounceRate", 0), prev.get("bounceRate", 0)))),
            ("Duração Média", _fmt_duration(curr.get("averageSessionDuration", 0)), _fmt_delta(_pct_delta(curr.get("averageSessionDuration", 0), prev.get("averageSessionDuration", 0)))),
            ("Engajamento", f"{_engagement_emoji(curr.get('engagementRate', 0))} {_fmt_pct(curr.get('engagementRate', 0))}", _fmt_delta(_pct_delta(curr.get("engagementRate", 0), prev.get("engagementRate", 0)))),
            ("Conversões", f"{curr.get('conversions', 0):.1f}", _fmt_delta(_pct_delta(curr.get("conversions", 0), prev.get("conversions", 0)))),
        ]
        for label, val, delta in kpi_rows:
            lines.append(f"| {label} | {val} | {delta} |")
    else:
        lines += [
            "### KPIs Principais",
            "",
            "| Métrica | Valor |",
            "|---------|-------|",
            f"| Sessões | {curr.get('sessions', 0):,} |",
            f"| Usuários Ativos | {curr.get('activeUsers', 0):,} |",
            f"| Novos Usuários | {curr.get('newUsers', 0):,} |",
            f"| Pageviews | {curr.get('screenPageViews', 0):,} |",
            f"| Bounce Rate | {_bounce_emoji(curr.get('bounceRate', 0))} {_fmt_pct(curr.get('bounceRate', 0))} |",
            f"| Duração Média | {_fmt_duration(curr.get('averageSessionDuration', 0))} |",
            f"| Engajamento | {_engagement_emoji(curr.get('engagementRate', 0))} {_fmt_pct(curr.get('engagementRate', 0))} |",
            f"| Conversões | {curr.get('conversions', 0):.1f} |",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Traffic Sources
# ---------------------------------------------------------------------------

def format_traffic_sources(data: dict[str, Any], start: str, end: str) -> str:
    rows = data.get("rows", [])
    group_by = data.get("group_by", "channel")
    count = data.get("count", 0)

    group_labels = {
        "channel": "Canal",
        "source_medium": "Fonte / Mídia",
        "campaign": "Campanha",
    }
    group_label = group_labels.get(group_by, group_by)

    lines = [
        f"## 🔀 Fontes de Tráfego — {start} a {end}",
        f"Agrupado por: **{group_label}** | **{count}** entradas",
        "",
    ]

    if not rows:
        lines.append("_Sem dados para o período informado._")
        return "\n".join(lines)

    lines += [
        f"| {group_label} | Sessões | Usuários | Novos | Bounce | Engaj. | Conv. |",
        "|" + "---|" * 7,
    ]

    for row in rows:
        label = row.get("label", "")
        lines.append(
            f"| {label} "
            f"| {row['sessions']:,} "
            f"| {row['active_users']:,} "
            f"| {row['new_users']:,} "
            f"| {_bounce_emoji(row['bounce_rate'])} {_fmt_pct(row['bounce_rate'])} "
            f"| {_engagement_emoji(row['engagement_rate'])} {_fmt_pct(row['engagement_rate'])} "
            f"| {row['conversions']:.1f} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Top Pages
# ---------------------------------------------------------------------------

def format_top_pages(data: dict[str, Any], start: str, end: str) -> str:
    pages = data.get("pages", [])
    count = data.get("count", 0)
    path_filter = data.get("filter")

    header = f"## 📄 Top Páginas — {start} a {end}"
    if path_filter:
        header += f" _(filtro: `{path_filter}*`)_"

    lines = [header, f"**{count}** páginas encontradas", ""]

    if not pages:
        lines.append("_Nenhuma página encontrada para os filtros informados._")
        return "\n".join(lines)

    lines += [
        "| # | Página | Pageviews | Sessões | Bounce | Duração |",
        "|---|--------|-----------|---------|--------|---------|",
    ]

    for i, page in enumerate(pages, 1):
        title = page.get("title") or page.get("path", "")
        path = page.get("path", "")
        display = f"{title}" if title and title != path else path
        lines.append(
            f"| {i} "
            f"| {display} "
            f"| {page['pageviews']:,} "
            f"| {page['sessions']:,} "
            f"| {_bounce_emoji(page['bounce_rate'])} {_fmt_pct(page['bounce_rate'])} "
            f"| {_fmt_duration(page['avg_session_duration'])} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Geographic Performance
# ---------------------------------------------------------------------------

def format_geographic_performance(data: dict[str, Any], start: str, end: str) -> str:
    locations = data.get("locations", [])
    granularity = data.get("granularity", "country")
    count = data.get("count", 0)

    gran_labels = {"country": "País", "region": "Região", "city": "Cidade"}
    gran_label = gran_labels.get(granularity, granularity)

    lines = [
        f"## 🗺️ Performance Geográfica — {start} a {end}",
        f"Granularidade: **{gran_label}** | **{count}** localidades",
        "",
    ]

    if not locations:
        lines.append("_Nenhuma localidade encontrada para os filtros informados._")
        return "\n".join(lines)

    lines += [
        f"| {gran_label} | Sessões | Usuários | Novos | Conv. | Bounce |",
        "|" + "---|" * 6,
    ]

    for loc in locations:
        lines.append(
            f"| {loc['name']} "
            f"| {loc['sessions']:,} "
            f"| {loc['active_users']:,} "
            f"| {loc['new_users']:,} "
            f"| {loc['conversions']:.1f} "
            f"| {_bounce_emoji(loc['bounce_rate'])} {_fmt_pct(loc['bounce_rate'])} |"
        )

    # Destaques
    with_sessions = [loc for loc in locations if loc["sessions"] > 0]
    if with_sessions:
        best_conv = max(with_sessions, key=lambda x: x["conversions"])
        if best_conv["conversions"] > 0:
            lines += [
                "",
                f"**Maior número de conversões:** {best_conv['name']} — "
                f"{best_conv['conversions']:.1f} conversões ({best_conv['sessions']:,} sessões)",
            ]

    no_conv = [loc for loc in locations if loc["conversions"] == 0 and loc["sessions"] > 0]
    if no_conv:
        worst = max(no_conv, key=lambda x: x["sessions"])
        lines.append(
            f"**Maior sessões sem conversão:** {worst['name']} — "
            f"{worst['sessions']:,} sessões sem retorno"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------

def format_audience(data: dict[str, Any], start: str, end: str) -> str:
    rows = data.get("rows", [])
    breakdown = data.get("breakdown", "deviceCategory")
    count = data.get("count", 0)

    breakdown_labels = {
        "deviceCategory": "Dispositivo",
        "browser": "Navegador",
        "operatingSystem": "Sistema Operacional",
    }
    breakdown_label = breakdown_labels.get(breakdown, breakdown)

    lines = [
        f"## 👥 Audiência por {breakdown_label} — {start} a {end}",
        f"**{count}** entradas",
        "",
    ]

    if not rows:
        lines.append("_Sem dados para o período informado._")
        return "\n".join(lines)

    lines += [
        f"| {breakdown_label} | Sessões | Usuários | Pageviews | Bounce | Engaj. |",
        "|" + "---|" * 6,
    ]

    for row in rows:
        lines.append(
            f"| {row['name']} "
            f"| {row['sessions']:,} "
            f"| {row['active_users']:,} "
            f"| {row['pageviews']:,} "
            f"| {_bounce_emoji(row['bounce_rate'])} {_fmt_pct(row['bounce_rate'])} "
            f"| {_engagement_emoji(row['engagement_rate'])} {_fmt_pct(row['engagement_rate'])} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def format_events(data: dict[str, Any], start: str, end: str) -> str:
    events = data.get("events", [])
    count = data.get("count", 0)
    event_filter = data.get("filter")

    header = f"## ⚡ Eventos — {start} a {end}"
    if event_filter:
        filter_str = ", ".join(f"`{e}`" for e in event_filter)
        header += f" _(filtro: {filter_str})_"

    lines = [header, f"**{count}** eventos encontrados", ""]

    if not events:
        lines.append("_Nenhum evento encontrado para os filtros informados._")
        return "\n".join(lines)

    lines += [
        "| # | Evento | Total | Por Usuário | Usuários |",
        "|---|--------|-------|-------------|----------|",
    ]

    for i, event in enumerate(events, 1):
        lines.append(
            f"| {i} "
            f"| {event['name']} "
            f"| {event['count']:,} "
            f"| {event['count_per_user']:.2f} "
            f"| {event['total_users']:,} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------

def format_conversions(data: dict[str, Any], start: str, end: str) -> str:
    conversions = data.get("conversions", [])
    totals = data.get("totals", {})
    count = data.get("count", 0)

    lines = [
        f"## 🎯 Conversões — {start} a {end}",
        f"**{count}** combinações canal/evento encontradas",
        "",
        f"**Total de conversões:** {totals.get('conversions', 0):.1f}",
        f"**Receita total:** R$ {totals.get('revenue', 0):,.2f}",
        "",
    ]

    if not conversions:
        lines.append("_Nenhuma conversão encontrada para o período informado._")
        return "\n".join(lines)

    lines += [
        "| Canal | Evento | Conversões | Receita | Sessões |",
        "|-------|--------|------------|---------|---------|",
    ]

    for row in conversions:
        lines.append(
            f"| {row['channel'] or '(not set)'} "
            f"| {row['event_name']} "
            f"| {row['conversions']:.1f} "
            f"| R$ {row['revenue']:,.2f} "
            f"| {row['sessions']:,} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Realtime
# ---------------------------------------------------------------------------

def format_realtime(data: dict[str, Any]) -> str:
    active_users = data.get("active_users", 0)
    by_page = data.get("by_page", [])
    by_source = data.get("by_source", [])
    by_country = data.get("by_country", [])
    by_device = data.get("by_device", [])

    lines = [
        "## 🔴 Dados em Tempo Real",
        "_Atualizado agora_",
        "",
        f"**Usuários ativos agora: {active_users}**",
        "",
    ]

    if by_page:
        lines += ["### Por Página", "", "| Página | Usuários Ativos |", "|--------|----------------|"]
        for item in by_page:
            lines.append(f"| {item['page']} | {item['active_users']} |")
        lines.append("")

    if by_source:
        lines += ["### Por Fonte", "", "| Fonte | Usuários Ativos |", "|-------|----------------|"]
        for item in by_source:
            lines.append(f"| {item['source'] or '(direct)'} | {item['active_users']} |")
        lines.append("")

    if by_country:
        lines += ["### Por País", "", "| País | Usuários Ativos |", "|------|----------------|"]
        for item in by_country:
            lines.append(f"| {item['country']} | {item['active_users']} |")
        lines.append("")

    if by_device:
        lines += ["### Por Dispositivo", "", "| Dispositivo | Usuários Ativos |", "|-------------|----------------|"]
        for item in by_device:
            lines.append(f"| {item['device']} | {item['active_users']} |")

    return "\n".join(lines)
