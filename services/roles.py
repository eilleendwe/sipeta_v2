"""Kunci dan label peran. Satu-satunya tempat nama peran didefinisikan."""

USER = "user"
ADMIN = "admin"
SUPERADMIN = "superadmin"

# Urutan menentukan sifat kumulatif: peran di kanan mewarisi hak peran di kiri.
ORDER = [USER, ADMIN, SUPERADMIN]

LABELS = {
    USER: "Pengguna",
    ADMIN: "Admin",
    SUPERADMIN: "Super Admin",
}


def label(role: str) -> str:
    return LABELS.get(role, role)


def level(role: str | None) -> int:
    return ORDER.index(role) if role in ORDER else -1


def has_role(role: str | None, minimum: str) -> bool:
    """True jika `role` setara atau lebih tinggi dari `minimum`."""
    return level(role) >= level(minimum)
