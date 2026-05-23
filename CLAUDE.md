# Contexto del proyecto — Agentic RAG sobre Grafo Ontológico

Este repositorio implementa un tutorial end-to-end (versión escrita en Colab) que muestra cómo:

1. Definir una **ontología** para un dominio acotado (actas de fútbol FCF).
2. Poblar un **grafo Neo4J** desde PDFs usando un **VLM** (sin OCR, solo visión).
3. Construir un **agente** que responde preguntas en lenguaje natural traduciéndolas a Cypher con tool-calling.

## Estado actual (2026-05-23)

- Las **5 etapas originales** (§1–8 de PLAN.md) están completas con un dataset de 3 actas de ejemplo en `data/documents/`.
- En curso: **pivot al dataset oficial completo** de 1793 actas (`data/pages1793/`), con un swap planificado de OpenAI GPT-4o a un **VLM local** corriendo en servidor GPU. Detalles en PLAN.md §10–§13.
- En curso: **split del tutorial en dos partes** — Part 1 (laboratorio interactivo, 3 actas) + Part 2 (operacional, 1793 actas). Detalles en PLAN.md §12.

## Antes de tocar nada

1. **Lee `PLAN.md` completo.** Es el documento normativo. Si hay conflicto entre este archivo y `PLAN.md`, gana `PLAN.md`.
2. Revisa la sección 8 de `PLAN.md` (checklist legacy v1) y la §14 (checklist v2 del pivot) para saber dónde quedó el trabajo.
3. Inspecciona `data/extracted/`, `data/extracted_full/` y `out/` para no re-ejecutar artefactos ya generados (la extracción VLM cuesta tokens / GPU-hours).

## Handoff al server-Claude (GPU box, VLM local)

Si estás corriendo este repo en un servidor con GPU y debes producir los artefactos masivos para el dataset 1793:

1. Implementa `src/extraction/vlm_local.py::extract()`. El contrato y sugerencias de modelos están en el docstring del archivo (Qwen2-VL, InternVL2, Pixtral, LLaVA-NeXT). Reutiliza `src.extraction.vlm_extractor._SYSTEM_PROMPT` verbatim — está afinado sobre los 3 ejemplos.
2. Corre `python scripts/bulk_convert_pdfs.py` (no necesita GPU, solo poppler).
3. Corre `python scripts/bulk_extract.py --provider local --workers 1`.
4. Comprime `data/images_full/` y `data/extracted_full/` por separado y entrégaselos al usuario para subirlos a Google Drive (uno por carpeta).
5. **NO toques el notebook ni `src/extraction/vlm_extractor.py`** — el notebook sigue usando OpenAI (en cantidad mínima: demo de 1-3 actas) y el rewire de descargas lo hace el Claude del laptop una vez tenga los IDs de GDrive.

## Reglas siempre activas

- **No usar OCR.** La única entrada al VLM son imágenes de los PDFs.
- **Compatibilidad Colab obligatoria.** Sin Docker, sin paths absolutos, sin GUIs. Neo4J es **AuraDB cloud**. Detalles en `PLAN.md` §3 y §6.8.
- **IDs deterministas y centralizados** en `src/common/ids.py`. Misma función en extractor e ingestor.
- **Idempotencia.** Todo Cypher de ingesta con `MERGE`. Caché en disco para extracciones VLM.
- **Cypher parametrizado.** Nunca interpolar datos en strings de Cypher. El agente opera en modo read-only (filtro en `src/agent/tools.py::run_cypher`).
- **Visualizadores duales.** Cada `render_*` escribe a `out/` y devuelve un objeto displayable inline.
- **Secretos** desde `src/common/config.py::get_secret()` — nunca leer `os.environ` ni `.env` directamente desde otros módulos.
- **Entornos Python con `uv venv` / `uv pip install`**, nunca pip directo.
- **No crear archivos `.md` adicionales.** Solo este `CLAUDE.md` y `PLAN.md`.
- **Actualiza el checklist** de `PLAN.md` (§8 para legacy, §14 para v2) al cierre de cada etapa.

## Stack rápido

Python 3.11+ · OpenAI (`gpt-4o`, sólo para demo y agente) · VLM local (server, swap pendiente) · Neo4J 5 (Aura) · Pydantic v2 · `pdf2image` (+poppler) · `graphviz` · `pyvis` · `rich` · `tenacity`.

## Layouts de datos

- `data/documents/example{1,2,3}.pdf` — 3 actas de ejemplo (lab, Part 1 del tutorial).
- `data/images/`, `data/extracted/` — PNGs y JSONs de los 3 ejemplos.
- `data/pages1793/*.pdf` — dataset oficial completo (1793 actas).
- `data/images_full/`, `data/extracted_full/` — artefactos masivos (poblados por `scripts/bulk_*.py`).

## Entry points

- **`tutorial.py`** — orquestador CLI legacy: `check`, `stage1`..`stage4 ask`, `repl`, `demo`, `all`. Funciona con los 3 ejemplos.
- **`scripts/bulk_convert_pdfs.py`** — convierte los 1793 PDFs a PNG (sin modelo).
- **`scripts/bulk_extract.py`** — corre VLM sobre los 1793 PNGs. `--provider openai|local`, resume desde caché, log de fallos en `_failures.jsonl`.
- **`summer_school_document_agentic_rag_tutorial.ipynb`** — notebook canónico para Colab (lo edita el equipo). Va a convertirse en **Part 2** después del rewire (PLAN.md §11).
- **`summer_school_part1_lab.ipynb`** — pendiente de crear (Part 1, PLAN.md §12).
