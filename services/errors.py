class ServiceError(Exception):
    """Galat yang pesannya aman ditampilkan langsung ke pengguna."""

    def __init__(self, message: str, fields: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        # Pesan per field form (kunci = nama field), jika ada.
        self.fields = fields or {}
