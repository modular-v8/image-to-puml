class UmlRegenError(Exception):
    """Base for every error this package raises intentionally."""

    exit_code = 1


class DependencyMissing(UmlRegenError):
    """A required external tool (java, dot, plantuml.jar) was not found."""

    exit_code = 2


class ProviderAuthError(UmlRegenError):
    """The configured vision provider rejected the credentials."""

    exit_code = 3


class ProviderRateLimited(UmlRegenError):
    """The configured vision provider is rate-limiting requests."""

    exit_code = 3


class ExtractionInvalid(UmlRegenError):
    """The provider's response failed IR schema validation, even after a repair retry."""

    exit_code = 4

    def __init__(self, message: str, *, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class NoClassesFound(UmlRegenError):
    """Extraction completed but found no classes in the image."""

    exit_code = 4


class ResponseTruncated(UmlRegenError):
    """The provider's response hit the token cap on the original attempt
    and again on a retry with the cap raised (T4.17)."""

    exit_code = 4

    def __init__(self, message: str, *, raw_response: str | None = None, token_cap: int | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.token_cap = token_cap


class RepetitionDetected(UmlRegenError):
    """The provider's response entered a degenerate repetition loop
    (a short unit repeated many times consecutively) instead of producing
    real content -- T3.37's original sighting, generalized by T4.18 after
    T3.28 found it recurring on a different model."""

    exit_code = 4

    def __init__(self, message: str, *, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class ExtractionDeclined(UmlRegenError):
    """Stage A reported zero classes both on the original attempt and
    after a reframed retry -- a genuine model decline (T3.28's third
    failure mode), not a JSON parse failure and not a token-budget issue."""

    exit_code = 4

    def __init__(self, message: str, *, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class InvalidImage(UmlRegenError):
    """The input file failed validation before extraction ever started:
    unreadable/corrupt, an unsupported format, or exceeding the
    decompression-bomb pixel limit (T4.12)."""

    exit_code = 6


class RenderFailed(UmlRegenError):
    """PlantUML failed to render the generated .puml source."""

    exit_code = 5

    def __init__(self, message: str, *, puml_source: str, stderr: str) -> None:
        super().__init__(message)
        self.puml_source = puml_source
        self.stderr = stderr
