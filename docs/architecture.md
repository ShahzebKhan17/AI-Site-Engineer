# Architecture

```text
PDF drawing → extraction → chunks with page citations → hybrid retrieval
                                                       ↓
Engineer question → structured, cited calculation request → Python engine → reviewed result
```

The retrieval layer can retrieve evidence but cannot calculate structural values. The calculation service accepts explicit dimensions, source references, and rule-derived values only. It returns a reproducible breakdown suitable for engineer review.

`hybrid_search_document_chunks` combines full-text ranking, vector similarity, and an exact entity-code boost. Project filtering and the database's Row Level Security policies ensure one project cannot retrieve another project's chunks.
