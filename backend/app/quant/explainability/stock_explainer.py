"""Evidence-grounded narrative explanations for stock research results.

The language model never receives a free-form user prompt. It can only summarize
the compact, server-computed evidence bundle assembled in this module. A fully
deterministic narrative remains available when the OpenAI API is not configured
or a provider request fails.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any, Final, Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from app.schemas.dashboard import (
    ExplanationEvidence,
    StockAnalysisResponse,
    StockExplanationResponse,
)

DEFAULT_MODEL: Final = "gpt-6-luna"
ExplanationLocale = Literal["en", "zh-CN"]
EXPLANATION_INSTRUCTIONS: Final = """You are a quantitative research editor.
Explain only the numeric evidence supplied by the application. Do not introduce
news, causal explanations, company events, price targets, forecasts, or facts
that are absent from the input. Never recommend buying, selling, holding, or
changing a portfolio. Use precise, neutral language and distinguish historical
measurements from current cross-sectional snapshots. Return a concise research
summary and two to four observations. Do not contradict the supplied risk label,
evidence interpretations, limitations, or disclaimer."""


class NarrativeDraft(BaseModel):
    """Structured subset authored by the model."""

    summary: str = Field(min_length=20, max_length=700)
    observations: list[str] = Field(min_length=2, max_length=4)


def generate_stock_explanation(
    analysis: StockAnalysisResponse,
    *,
    api_key: str | None = None,
    model: str | None = None,
    client: Any | None = None,
    locale: ExplanationLocale = "en",
) -> StockExplanationResponse:
    """Explain a computed stock analysis without producing investment advice.

    ``client`` is injectable so the OpenAI boundary can be tested without a
    network request. Passing ``api_key=""`` explicitly selects deterministic
    mode even when the process environment contains a key.
    """

    evidence = _build_evidence(analysis, locale=locale)
    risk_level = _risk_level(analysis.risk.annualized_volatility)
    limitations = _limitations(analysis, locale=locale)
    resolved_model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    resolved_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key

    if client is None and not resolved_key:
        return _deterministic_response(
            analysis,
            evidence=evidence,
            risk_level=risk_level,
            limitations=limitations,
            provider_message=_provider_message(locale, configured=False),
            locale=locale,
        )

    payload = {
        "ticker": analysis.ticker,
        "risk_level": risk_level,
        "evidence": [item.model_dump() for item in evidence],
        "limitations": limitations,
        "ml_experiment": {
            "status": analysis.ml_experiment.status,
            "message": analysis.ml_experiment.message,
        },
        "output_language": "Simplified Chinese" if locale == "zh-CN" else "English",
    }
    try:
        sdk_client = client or OpenAI(api_key=resolved_key)
        response = sdk_client.responses.parse(
            model=resolved_model,
            instructions=(
                f"{EXPLANATION_INSTRUCTIONS}\nWrite all generated prose in "
                f"{'Simplified Chinese' if locale == 'zh-CN' else 'English'}."
            ),
            input=json.dumps(payload, ensure_ascii=False),
            text_format=NarrativeDraft,
            max_output_tokens=500,
            store=False,
        )
        draft = response.output_parsed
        if draft is None:
            raise RuntimeError("OpenAI returned no parsed explanation.")
    except Exception:
        return _deterministic_response(
            analysis,
            evidence=evidence,
            risk_level=risk_level,
            limitations=limitations,
            provider_message=_provider_message(locale, configured=True),
            locale=locale,
        )

    return StockExplanationResponse(
        ticker=analysis.ticker,
        summary=draft.summary,
        risk_level=risk_level,
        observations=draft.observations,
        evidence=evidence,
        limitations=limitations,
        source="openai",
        model=resolved_model,
        provider_message=(
            "基于页面所示指标通过 OpenAI 结构化输出生成。"
            if locale == "zh-CN"
            else "Generated from the displayed metrics with OpenAI Structured Outputs."
        ),
        generated_at_utc=datetime.now(UTC).isoformat(),
        disclaimer=_disclaimer(locale),
    )


def _deterministic_response(
    analysis: StockAnalysisResponse,
    *,
    evidence: list[ExplanationEvidence],
    risk_level: Literal["Lower", "Moderate", "Elevated"],
    limitations: list[str],
    provider_message: str,
    locale: ExplanationLocale,
) -> StockExplanationResponse:
    factor_description = _factor_description(analysis.factor_score.total)
    return_direction = "positive" if analysis.risk.annualized_return >= 0 else "negative"
    if locale == "zh-CN":
        factor_cn = {"strong": "较强", "mixed": "均衡", "weak": "较弱"}[factor_description]
        return_cn = "为正" if return_direction == "positive" else "为负"
        risk_cn = {"Lower": "较低", "Moderate": "中等", "Elevated": "较高"}[risk_level]
        summary = (
            f"{analysis.ticker} 在当前 {analysis.factor_score.universe_size} 只股票样本中呈现"
            f"{factor_cn}的综合因子特征，历史年化收益率{return_cn}。其"
            f" {analysis.risk.annualized_volatility:.1%} 的年化波动率和"
            f" {analysis.risk.maximum_drawdown:.1%} 的最大回撤对应{risk_cn}描述性风险。"
        )
    else:
        summary = (
            f"{analysis.ticker} has a {factor_description} factor profile in the displayed "
            f"{analysis.factor_score.universe_size}-stock universe and a {return_direction} "
            f"historical annualized return. Its {analysis.risk.annualized_volatility:.1%} "
            f"annualized volatility and {analysis.risk.maximum_drawdown:.1%} maximum drawdown "
            f"place the descriptive risk label at {risk_level.lower()}."
        )
    observations = [
        evidence[0].interpretation,
        evidence[1].interpretation,
        evidence[2].interpretation,
    ]
    return StockExplanationResponse(
        ticker=analysis.ticker,
        summary=summary,
        risk_level=risk_level,
        observations=observations,
        evidence=evidence,
        limitations=limitations,
        source="deterministic",
        model=None,
        provider_message=provider_message,
        generated_at_utc=datetime.now(UTC).isoformat(),
        disclaimer=_disclaimer(locale),
    )


def _build_evidence(
    analysis: StockAnalysisResponse, *, locale: ExplanationLocale
) -> list[ExplanationEvidence]:
    factor = analysis.factor_score
    risk = analysis.risk
    strongest_name, strongest_score = max(
        (("Value", factor.value), ("Momentum", factor.momentum), ("Quality", factor.quality)),
        key=lambda item: item[1],
    )
    weakest_name, weakest_score = min(
        (("Value", factor.value), ("Momentum", factor.momentum), ("Quality", factor.quality)),
        key=lambda item: item[1],
    )
    if locale == "zh-CN":
        factor_names = {"Value": "价值", "Momentum": "动量", "Quality": "质量"}
        return [
            ExplanationEvidence(
                label="因子特征",
                value=f"{factor.total:.1f}/100 · 排名 {factor.rank}/{factor.universe_size}",
                interpretation=(
                    f"{factor_names[strongest_name]}是最强的相对因子，得分 "
                    f"{strongest_score:.1f}；{factor_names[weakest_name]}最弱，得分 "
                    f"{weakest_score:.1f}。"
                ),
            ),
            ExplanationEvidence(
                label="历史收益",
                value=f"年化 {risk.annualized_return:.1%}",
                interpretation=(
                    f"{risk.start_date} 至 {risk.end_date} 的几何年化收益率仅描述该历史样本，"
                    "并非未来收益估计。"
                ),
            ),
            ExplanationEvidence(
                label="历史风险",
                value=(
                    f"波动率 {risk.annualized_volatility:.1%} · "
                    f"最大回撤 {risk.maximum_drawdown:.1%}"
                ),
                interpretation="波动率衡量收益离散程度，最大回撤记录样本中最大的峰谷跌幅。",
            ),
            ExplanationEvidence(
                label="尾部损失估计",
                value=f"单日 VaR {risk.value_at_risk:.2%} · 置信度 {risk.var_confidence_level:.0%}",
                interpretation="历史 VaR 是样本分位数，不能描述超过该阈值的损失程度。",
            ),
        ]
    return [
        ExplanationEvidence(
            label="Factor profile",
            value=(f"{factor.total:.1f}/100 · rank {factor.rank}/{factor.universe_size}"),
            interpretation=(
                f"{strongest_name} is the strongest relative component at "
                f"{strongest_score:.1f}, while {weakest_name} is the weakest at "
                f"{weakest_score:.1f}."
            ),
        ),
        ExplanationEvidence(
            label="Historical return",
            value=f"{risk.annualized_return:.1%} annualized",
            interpretation=(
                f"The geometric annualized return over {risk.start_date} to {risk.end_date} "
                "describes the sample and is not a forward return estimate."
            ),
        ),
        ExplanationEvidence(
            label="Historical risk",
            value=(
                f"{risk.annualized_volatility:.1%} volatility · "
                f"{risk.maximum_drawdown:.1%} max drawdown"
            ),
            interpretation=(
                "Volatility measures dispersion, while maximum drawdown records the "
                "largest observed peak-to-trough decline in the sample."
            ),
        ),
        ExplanationEvidence(
            label="Tail-loss estimate",
            value=(
                f"{risk.value_at_risk:.2%} one-day VaR at "
                f"{risk.var_confidence_level:.0%} confidence"
            ),
            interpretation=(
                "Historical VaR is a sample quantile and does not describe losses beyond "
                "the threshold."
            ),
        ),
    ]


def _risk_level(volatility: float) -> Literal["Lower", "Moderate", "Elevated"]:
    if volatility < 0.25:
        return "Lower"
    if volatility < 0.45:
        return "Moderate"
    return "Elevated"


def _factor_description(score: float) -> str:
    if score >= 67.0:
        return "strong"
    if score >= 40.0:
        return "mixed"
    return "weak"


def _limitations(analysis: StockAnalysisResponse, *, locale: ExplanationLocale) -> list[str]:
    if locale == "zh-CN":
        limitations = [
            "风险标签是基于波动率的描述性规则，并非投资者适配度评估。",
            "因子得分相对于当前小样本股票池计算，并会随时间变化。",
            "历史收益、回撤和 VaR 不能预测未来表现或尾部损失。",
        ]
        limitations.append(
            "机器学习数值是历史留出集结果，并非实时预测。"
            if analysis.ml_experiment.status == "available"
            else "该股票目前没有已保存的机器学习实验。"
        )
        return limitations
    limitations = [
        "The risk label is a descriptive volatility heuristic, not a suitability assessment.",
        "Factor scores are relative to a small current-snapshot universe and can change over time.",
        "Historical return, drawdown, and VaR do not forecast future performance or tail losses.",
    ]
    if analysis.ml_experiment.status == "available":
        limitations.append(
            "Machine-learning values are historical holdout results, not live predictions."
        )
    else:
        limitations.append("No saved machine-learning experiment is available for this ticker.")
    return limitations


def _provider_message(locale: ExplanationLocale, *, configured: bool) -> str:
    if locale == "zh-CN":
        return (
            "OpenAI 暂时不可用；当前显示基于相同证据生成的确定性解释。"
            if configured
            else "尚未配置 OPENAI_API_KEY；当前显示基于证据生成的确定性解释。"
        )
    return (
        "OpenAI was unavailable; showing the deterministic evidence-based explanation."
        if configured
        else (
            "OPENAI_API_KEY is not configured; showing the deterministic "
            "evidence-based explanation."
        )
    )


def _disclaimer(locale: ExplanationLocale) -> str:
    if locale == "zh-CN":
        return "AI 仅解释已提供的研究数据，不构成投资建议。"
    return "AI explains supplied research data only; it does not provide investment advice."
