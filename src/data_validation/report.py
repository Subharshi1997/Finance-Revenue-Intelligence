"""Renders per-table findings and cross-table findings into a Markdown
data-quality report."""
from __future__ import annotations

import pandas as pd


def _format_counts(d: dict) -> str:
    if not d:
        return "None found\n"
    return "".join(f"- {k}: {v}\n" for k, v in d.items())


def render_table_section(findings: dict) -> str:
    lines = [f"## {findings['table']}\n", f"Rows: {findings['rows']:,}\n"]

    lines.append("\n**Missing required values**\n")
    lines.append(_format_counts(findings["missing_values"]))

    lines.append("\n**Duplicate primary key rows**\n")
    lines.append(f"{findings['duplicate_ids']}\n")

    if "duplicate_business_rows" in findings:
        lines.append("\n**Duplicate transactions (same merchant/order/date/amount)**\n")
        lines.append(f"{findings['duplicate_business_rows']}\n")

    lines.append("\n**Invalid or out-of-range dates**\n")
    lines.append(_format_counts(findings["invalid_dates"]))

    lines.append("\n**Date sequence violations**\n")
    lines.append(_format_counts(findings["date_order_violations"]))

    lines.append("\n**Negative amounts**\n")
    lines.append(_format_counts(findings["negative_amounts"]))

    lines.append("\n**Invalid rates (outside 0-15%)**\n")
    lines.append(_format_counts(findings["invalid_rates"]))

    lines.append("\n**Invalid categorical values**\n")
    lines.append(_format_counts(findings["invalid_categorical_values"]))

    lines.append("\n**Referential integrity violations**\n")
    lines.append(_format_counts(findings["referential_integrity_violations"]))

    return "".join(lines) + "\n"


def render_cross_table_section(
    missing_invoices: pd.DataFrame,
    duplicate_payments: pd.DataFrame,
    unmatched_payments: pd.DataFrame,
    orphan_payments: pd.DataFrame,
    invoices_without_payment: pd.DataFrame,
    amount_mismatches: pd.DataFrame,
) -> str:
    lines = ["## Cross-table finance checks\n"]
    lines.append(
        f"\n**Missing invoices** (merchant-months with successful transactions but no invoice): "
        f"{len(missing_invoices):,}\n"
    )
    lines.append(f"\n**Duplicate payments** (same invoice + amount paid more than once): {len(duplicate_payments):,}\n")
    lines.append(f"\n**Unmatched payments** (payment references a non-existent invoice_id): {len(unmatched_payments):,}\n")
    lines.append(f"\n**Orphan payments** (cash received with no invoice_id to apply it against): {len(orphan_payments):,}\n")
    lines.append(f"\n**Invoices with no payment recorded** (open AR balance): {len(invoices_without_payment):,}\n")
    lines.append(f"\n**Invoice/payment amount mismatches** (paid total != invoice total): {len(amount_mismatches):,}\n")
    lines.append(
        "\nThese are not treated as ingestion errors and are left in the cleaned dataset - "
        "they are the business exceptions that the reconciliation engine (Phase 7) and revenue "
        "leakage engine (Phase 8) are built to quantify.\n"
    )
    return "".join(lines)


def render_cleaning_section(cleaning_stats: dict[str, dict]) -> str:
    lines = ["## Cleaning actions applied\n"]
    lines.append(
        "\nOnly genuine ingestion garbage was corrected before loading into the SQL database - "
        "system-level duplicate IDs, orphan rows with no merchant reference, and physically "
        "invalid (negative) amounts. Business-meaningful exceptions were left in place.\n\n"
    )
    for table, stats in cleaning_stats.items():
        lines.append(f"**{table}**: {stats['rows_before']:,} -> {stats['rows_after']:,} rows\n")
        for k, v in stats.items():
            if k not in ("rows_before", "rows_after") and v:
                lines.append(f"- {k}: {v}\n")
        lines.append("\n")
    return "".join(lines)
