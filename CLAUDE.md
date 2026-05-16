# Contexto del proyecto — Agentic RAG sobre Grafo Ontológico

Este repositorio implementa un tutorial end-to-end que muestra cómo:

1. Definir una **ontología** para un dominio acotado (actas de fútbol FCF).
2. Poblar un **grafo Neo4J** desde PDFs usando **GPT-4o como VLM** (sin OCR, solo visión).
3. Construir un **agente** que responde preguntas en lenguaje natural traduciéndolas a Cypher con tool-calling.

## Antes de tocar nada

1. **Lee `PLAN.md` completo.** Es el documento normativo. Si hay conflicto entre este archivo y `PLAN.md`, gana `PLAN.md`.
2. Revisa la sección 8 de `PLAN.md` (checklist de progreso) para saber dónde quedó el trabajo.
3. Inspecciona `data/extracted/` y `out/` para no re-ejecutar artefactos ya generados (la extracción VLM cuesta tokens).

## Reglas siempre activas

- **No usar OCR.** La única entrada al VLM son imágenes de los PDFs.
- **Compatibilidad Colab obligatoria.** Sin Docker, sin paths absolutos, sin GUIs. Neo4J es **AuraDB cloud**. Detalles en `PLAN.md` §3 y §6.8.
- **IDs deterministas y centralizados** en `src/common/ids.py`. Misma función en extractor e ingestor.
- **Idempotencia.** Todo Cypher de ingesta con `MERGE`. Caché en disco para extracciones VLM.
- **Cypher parametrizado.** Nunca interpolar datos en strings de Cypher. El agente opera en modo read-only (filtro en `src/agent/tools.py::run_cypher`).
- **Visualizadores duales.** Cada `render_*` escribe a `out/` y devuelve un objeto displayable inline.
- **Secretos** desde `src/common/config.py::get_secret()` — nunca leer `os.environ` ni `.env` directamente desde otros módulos.
- **No crear archivos `.md` adicionales.** Solo este `CLAUDE.md` y `PLAN.md`.
- **Actualiza el checklist** de `PLAN.md` §8 al cierre de cada etapa.

## Stack rápido

Python 3.11+ · OpenAI (`gpt-4o`) · Neo4J 5 (Aura) · Pydantic v2 · `pdf2image` (+poppler) · `graphviz` · `pyvis` · `rich` · `tenacity`.

## Entry point

`tutorial.py` orquesta todo con subcomandos: `check`, `stage1`, `stage2`, `stage3`, `stage4 ask "..."`, `repl`, `demo`, `all`. Cada subcomando llama a funciones importables de `src/` — esas mismas funciones serán las celdas del notebook Colab al portar.
