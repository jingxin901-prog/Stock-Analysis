"""Validate the Phase 1 QuantAI repository scaffold without external packages."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRECTORIES = (
    "backend/app/api/v1/routes",
    "backend/app/core",
    "backend/app/db",
    "backend/app/quant/data",
    "backend/app/quant/metrics",
    "backend/app/quant/factors",
    "backend/app/quant/portfolio",
    "backend/app/quant/simulation",
    "backend/app/quant/ml",
    "backend/app/quant/explainability",
    "backend/app/schemas",
    "backend/app/services",
    "backend/tests/unit",
    "backend/tests/integration",
    "frontend/app/market-overview",
    "frontend/app/stock-analysis",
    "frontend/app/portfolio-optimizer",
    "frontend/components",
    "frontend/lib",
    "frontend/types",
    "frontend/tests",
    "data/raw",
    "data/interim",
    "data/processed",
    "artifacts",
    "notebooks",
    "configs",
    "docs",
)

REQUIRED_FILES = (
    ".editorconfig",
    ".env.example",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "research_report.md",
    "backend/app/quant/data/data_loader.py",
    "backend/app/quant/data/fundamental_loader.py",
    "backend/app/quant/factors/factor_model.py",
    "backend/app/quant/metrics/financial_metrics.py",
    "backend/app/quant/portfolio/optimizer.py",
    "backend/app/quant/portfolio/visualization.py",
    "backend/app/quant/simulation/monte_carlo.py",
    "backend/tests/unit/test_data_loader.py",
    "backend/tests/unit/test_factor_model.py",
    "backend/tests/unit/test_fundamental_loader.py",
    "backend/tests/unit/test_financial_metrics.py",
    "backend/tests/unit/test_monte_carlo.py",
    "backend/tests/unit/test_portfolio_optimizer.py",
    "backend/tests/integration/test_live_data_loader.py",
    "docs/architecture.md",
    "docs/data_validation.md",
    "docs/factor_model.md",
    "docs/financial_metrics.md",
    "docs/portfolio_optimization.md",
    "scripts/analyze_stock.py",
    "scripts/rank_stocks.py",
    "scripts/optimize_portfolio.py",
    "scripts/validate_market_data.py",
)


def main() -> int:
    missing = [
        relative_path
        for relative_path in (*REQUIRED_DIRECTORIES, *REQUIRED_FILES)
        if not (PROJECT_ROOT / relative_path).exists()
    ]

    if missing:
        print("QuantAI scaffold validation failed. Missing paths:")
        for relative_path in missing:
            print(f"- {relative_path}")
        return 1

    print(
        "QuantAI scaffold validation passed: "
        f"{len(REQUIRED_DIRECTORIES)} directories and "
        f"{len(REQUIRED_FILES)} files found."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
