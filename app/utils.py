from datetime import date


def format_rupiah(amount: int) -> str:
    """Format integer amount to Rupiah string like Rp 25.000."""
    if amount < 0:
        return f"- Rp {abs(amount):,.0f}".replace(",", ".")
    return f"Rp {amount:,.0f}".replace(",", ".")


def today_str() -> str:
    """Return today's date as ISO string."""
    return date.today().isoformat()
