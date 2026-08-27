from .result import ValidationResult


def format_validation_report(result: ValidationResult) -> str:
    lines = [
        "BLOCKSANGAM DATA VALIDATION",
        "=" * 28,
        f"Status: {result.status}",
        f"Errors: {len(result.errors)}",
        f"Warnings: {len(result.warnings)}",
    ]

    if result.errors:
        lines += ["", "ERRORS", "------"]
        for issue in result.errors:
            lines.append(f"[{issue.code}] {issue.entity_type}:{issue.entity_id} - {issue.message}")

    if result.warnings:
        lines += ["", "WARNINGS", "--------"]
        for issue in result.warnings:
            lines.append(f"[{issue.code}] {issue.entity_type}:{issue.entity_id} - {issue.message}")

    return "\n".join(lines)
