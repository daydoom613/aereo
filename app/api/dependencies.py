"""What a request handler is given: a database session and the service built on it."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.repositories.file_repository import FileRepository
from app.services.file_service import FileService


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_file_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> FileService:
    return FileService(FileRepository(session), request.app.state.readers)


FileServiceDependency = Annotated[FileService, Depends(get_file_service)]
