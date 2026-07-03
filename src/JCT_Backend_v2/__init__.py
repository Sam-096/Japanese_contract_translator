"""JCT_Backend_v2 — experimental layout-preserving JA->EN legal document pipeline.

Standalone from `jpdoc` (the production package backing the live app). Not
imported by `JCT_Backend_v1/`. Explores a different tech stack: GiNZA/spaCy NER
masking, a vLLM-targeted translation client, and WeasyPrint HTML/CSS
rendering instead of jpdoc's reportlab canvas.
"""
