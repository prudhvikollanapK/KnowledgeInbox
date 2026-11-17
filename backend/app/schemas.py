from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .fetcher import validate_url

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["note", "url"]
    content: Annotated[NonEmpty, Field(max_length=100_000)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)] = ""

    @model_validator(mode="after")
    def validate_source(self) -> "IngestRequest":
        if self.source_type == "url":
            if len(self.content) > 2048:
                raise ValueError("URLs must be at most 2,048 characters.")
            validate_url(self.content)
        return self


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[NonEmpty, Field(max_length=2000)]
    top_k: int = Field(default=5, ge=1, le=8)


class Item(BaseModel):
    id: str
    title: str
    source_type: Literal["note", "url"]
    url: str | None
    created_at: str
    status: Literal["pending", "processing", "ready", "failed"]
    error: str | None
    preview: str
    word_count: int
    chunk_count: int


class ItemDetail(Item):
    content: str
    resolved_url: str | None


class ItemList(BaseModel):
    items: list[Item]
    total: int
    has_more: bool


class Source(BaseModel):
    citation: int
    item_id: str
    chunk_id: str
    title: str
    source_type: Literal["note", "url"]
    url: str | None
    snippet: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    mode: Literal["openai", "demo"]
    insufficient_context: bool = False
    duration_ms: int
