"""Measured model usage for one process run. Nothing here is estimated."""


class Usage:
    def __init__(self) -> None:
        self.model_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.skipped_model = False
        self.providers: dict[str, dict[str, int]] = {}

    def note_skipped_model(self) -> None:
        self.skipped_model = True

    def as_dict(self) -> dict:
        total = self.input_tokens + self.output_tokens
        return {
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": total,
            "providers": self.providers,
            "skipped_model": self.skipped_model,
        }
