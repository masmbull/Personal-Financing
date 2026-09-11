"""Relevant emoji icon pools per account type (create/edit account forms)."""

from app.models.models import AccountType

# One pool per AccountType; the form picker shows only the pool matching the
# selected type. Icons mirror the seeded defaults in app/main.py.
ACCOUNT_ICON_POOLS = {
    AccountType.CASH: [
        "\U0001f4b5",  # banknote with dollar sign
        "\U0001f4b0",  # money bag
        "\U0001f4b8",  # money with wings
        "\U0001f4b1",  # currency exchange
        "\U0001f9fe",  # receipt
    ],
    AccountType.BANK: [
        "\U0001f3e6",  # bank
        "\U0001f3e2",  # office
        "\U0001f3db",  # classical building
        "\U0001f4bc",  # briefcase
        "\U0001f4b3",  # credit card
    ],
    AccountType.E_WALLET: [
        "\U0001f4f1",  # mobile phone
        "\U0001f4b3",  # credit card
        "\U0001f4f8",  # camera
        "\U0001f4e9",  # e-mail
        "\U0001f5a5",  # computer
    ],
    AccountType.SERVER_EMONEY: [
        "\U0001f4f1",  # mobile phone
        "\U0001f4b3",  # credit card
        "\U0001f4f8",  # camera
        "\U0001f4e9",  # e-mail
    ],
    AccountType.CARD_EMONEY: [
        "\U0001f4b3",  # credit card
        "\U0001f4bf",  # optical disc
        "\U0001f3e6",  # bank
    ],
    AccountType.CREDIT_CARD: [
        "\U0001f4b3",  # credit card
        "\U0001f4dd",  # memo
        "\U0001f4b0",  # money bag
        "\U0001f4bc",  # briefcase
    ],
    AccountType.PAY_LATER: [
        "\U0001f4b3",  # credit card
        "\U0001f4c5",  # calendar
        "\U0001f4dd",  # memo
        "\U0001f4f6",  # signal bars
    ],
    AccountType.SAVINGS: [
        "\U0001f437",  # pig face
        "\U0001f4b0",  # money bag
        "\U0001f4b1",  # currency exchange
        "\U0001f4b5",  # banknote
        "\U0001f9fe",  # receipt
    ],
    AccountType.LOAN: [
        "\U0001f4b8",  # money with wings
        "\U0001f3e6",  # bank
        "\U0001f4dd",  # memo
        "\U0001f4c9",  # chart decreasing
        "\U0001f4b5",  # banknote
    ],
    AccountType.INVESTMENT: [
        "\U0001f4c8",  # chart increasing
        "\U0001f4c9",  # chart decreasing
        "\U0001f4b0",  # money bag
        "\U0001f4bc",  # briefcase
        "\U0001f4e6",  # package
    ],
    AccountType.GOLD: [
        "\U0001f947",  # 1st place medal
        "\U0001f48d",  # gem stone
        "\U0001f4b0",  # money bag
        "\U0001f3c5",  # sports medal
    ],
    AccountType.ASSET: [
        "\U0001f3e0",  # house
        "\U0001f697",  # automobile
        "\U0001f6b2",  # bicycle
        "\U0001f3e1",  # house with garden
        "\U0001f3e2",  # office
    ],
    AccountType.LIABILITY: [
        "\U0001f4c9",  # chart decreasing
        "\U0001f4dd",  # memo
        "\U0001f4a5",  # collision
        "\U0001f4b8",  # money with wings
    ],
    AccountType.OTHER: [
        "\U0001f4e6",  # package
        "\U0001f4c4",  # page facing up
        "\U0001f4c5",  # calendar
        "\U0001f5c3",  # card file box
        "\U0001f6ce",  # bellhop bell
    ],
}


# Brand mark per Indonesian financial institution (lowercase substring ->
# (display mark, background colour, foreground colour)). Matched against the
# account's institution+name; the LONGEST matching key wins so e.g. "BCA
# Digital" resolves to blu before the generic "BCA" key. Hand-maintained,
# deliberately small.
BANK_BRANDS = {
    "bca digital": ("blu", "#2b3a8f", "#ffffff"),
    "bca": ("BCA", "#0060af", "#ffffff"),
    "mandiri": ("M", "#003b7c", "#ffc832"),
    "bni": ("BNI", "#f7941e", "#00437a"),
    "bri": ("BRI", "#00529c", "#ffbf00"),
    "btn": ("BTN", "#0069b4", "#ffffff"),
    "cimb": ("CIMB", "#00258a", "#ffffff"),
    "danamon": ("D", "#0057a0", "#ffffff"),
    "permata": ("P", "#5f2d91", "#ffffff"),
    "maybank": ("M", "#ffd600", "#00296b"),
    "ocbc": ("OCBC", "#2d6cdf", "#ffffff"),
    "btpn": ("BTPN", "#d71921", "#ffffff"),
    "bank mega": ("M", "#003d79", "#ffd400"),
    "sinarmas": ("S", "#ee7d20", "#ffffff"),
    "panin": ("P", "#ed1c24", "#ffffff"),
    "uob": ("UOB", "#ec2028", "#ffffff"),
    "dbs": ("DBS", "#0058b0", "#ffffff"),
    "jago": ("J", "#ff6a13", "#ffffff"),
    "seabank": ("SB", "#14365f", "#ffffff"),
    "neo commerce": ("Neo", "#003c71", "#ffffff"),
    "allo": ("Allo", "#0066ff", "#ffffff"),
    "bsi": ("BSI", "#00843d", "#ffffff"),
    "muamalat": ("M", "#00a651", "#ffffff"),
    "gopay": ("G", "#00aa13", "#ffffff"),
    "ovo": ("O", "#4c2e91", "#ffffff"),
    "dana": ("D", "#1486e3", "#ffffff"),
    "shopeepay": ("SP", "#ee4d2d", "#ffffff"),
    "linkaja": ("L", "#002f6c", "#ffffff"),
    "i.saku": ("iS", "#0095d9", "#ffffff"),
}


# Bundled official logo per BANK_BRANDS key (app/static/bank-logos/<file>).
# Key without an entry (e.g. "bca digital"/blu) falls back to the monogram mark.
BRAND_LOGOS = {
    "bca": "bca.png", "mandiri": "mandiri.png", "bni": "bni.png",
    "bri": "bri.png", "btn": "btn.png", "cimb": "cimb.png",
    "danamon": "danamon.png", "permata": "permata.png", "maybank": "maybank.png",
    "ocbc": "ocbc.png", "btpn": "btpn.png", "bank mega": "mega.png",
    "sinarmas": "sinarmas.png", "panin": "panin.png", "uob": "uob.png",
    "dbs": "dbs.png", "jago": "jago.png", "seabank": "seabank.png",
    "neo commerce": "neo.png", "allo": "allo.png", "bsi": "bsi.png",
    "muamalat": "muamalat.png", "gopay": "gopay.png", "ovo": "ovo.png",
    "dana": "dana.png", "shopeepay": "shopeepay.png", "linkaja": "linkaja.png",
    "i.saku": "isaku.png",
}


def bank_brand(account) -> dict[str, str] | None:
    """Brand mark + colours + logo for BANK/E_WALLET accounts, else None (emoji fallback)."""
    if account.type not in (AccountType.BANK, AccountType.E_WALLET):
        return None
    haystack = " ".join(filter(None, (account.institution, account.name))).lower()
    for key in sorted(BANK_BRANDS, key=len, reverse=True):
        if key in haystack:
            mark, bg, fg = BANK_BRANDS[key]
            return {"mark": mark, "bg": bg, "fg": fg, "logo": BRAND_LOGOS.get(key)}
    return None