"""The four external boundaries. Later tickets widen these; callers depend only on these shapes."""

from typing import Protocol


class MyInvoisGateway(Protocol):
    def validate_tin(self, tin: str) -> bool: ...


class AIProvider(Protocol):
    def extract(self, document: bytes, schema: dict) -> dict: ...


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...
