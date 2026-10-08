"""The single error body, RFC 9457 Problem Details."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InvalidParameter(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    type: str = Field(default="about:blank", description="A URI identifying the problem type.")
    title: str = Field(description="The HTTP status phrase.")
    status: int
    detail: str = Field(description="What went wrong with this request.")
    instance: str = Field(description="The path of the request that failed.")
    errors: list[InvalidParameter] | None = Field(
        default=None, description="Present on 400 responses: the request parts that are invalid."
    )
