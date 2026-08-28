class GraphDeferredIllegalOperationError(TypeError):
    """Raised when a future (Socket) is used in an illegal concrete operation."""

    pass


class SocketValueError(ValueError):
    """A value the socket layer refused, carrying where it was refused.

    ``loc`` names the socket path below a task's inputs and ``type`` names the
    rule that refused, both spelled as pydantic spells them in
    ``ValidationError.errors()``: a caller reading a refusal does not have to
    know whether an input model or the socket layer produced it.
    """

    def __init__(
        self,
        message: str,
        *,
        loc: tuple = (),
        error_type: str = "",
    ) -> None:
        super().__init__(message)
        self.loc = tuple(loc)
        self.type = error_type
