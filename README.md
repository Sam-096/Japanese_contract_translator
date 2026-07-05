title: Japanese Contract Translator Backend
emoji: ⛩️
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false

Japanese Legal Contract Translator & OCR Hub

This Hugging Face Space operates as a dedicated high-performance OCR worker node in our hybrid translation microservice.

It handles intensive image and scanned PDF structures using the YomiToku and Manga-OCR neural pipeline engines, completely isolated from the lightweight database operations.

Architecture Integration

Orchestrator Core: Render (LOW_MEMORY_MODE=true)

OCR Compute Engine: Hugging Face Space (LOW_MEMORY_MODE=false)

Inter-Service Communication: Secured over HTTP using matching EXT_CLNT_KEY bearer-token authorization.