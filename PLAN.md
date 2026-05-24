# Plan: Agentic RAG sobre un Grafo Ontológico de Actas de Fútbol

> Documento maestro. Si vas a trabajar en este proyecto, **lee este archivo completo antes de tocar código**.
> Las convenciones de la sección 6 son normativas. El checklist de la sección 8 se actualiza a medida que avanzas.

---

## 1. Contexto y objetivo

El objetivo es construir un tutorial ejecutable (en `.py`, portable luego a Jupyter / Google Colab) que muestre, de extremo a extremo, un sistema **Agentic RAG sobre un grafo ontológico**:

1. Se parte de un dominio acotado: **actas oficiales de partidos de fútbol** de la Federació Catalana de Futbol (FCF).
2. Se diseña una **ontología** que organiza la información del dominio.
3. Se construye un **grafo Neo4J** que materializa esa ontología.
4. El grafo se **puebla a partir de PDFs** usando un **VLM (GPT-4o vía API)** que ve la página como imagen — sin OCR, sin parsing de texto.
5. Se implementa un **agente** que recibe consultas en lenguaje natural, las traduce a Cypher mediante tool-calling, las ejecuta contra el grafo, recupera ante errores y devuelve la respuesta parafraseada en lenguaje natural.

El tutorial tiene valor pedagógico: la audiencia podrá visualizar la ontología, el grafo poblado y el rastro completo del agente al razonar.

---

## 2. Dominio: estructura de un acta FCF

Hay 3 PDFs de ejemplo en `data/examples/` (`example1.pdf`, `example2.pdf`, `example3.pdf`). Todos siguen el mismo layout gráfico (idioma: catalán). Una acta contiene:

**Cabecera del partido**
- Fecha y hora de generación, jornada (`Jornada N`), competición (FCF), estado (`ACTA TANCADA`).
- Equipo local, equipo visitante, marcador final.

**Por cada equipo**
- **Titulares** (`TITULARS`): dorsal + nombre completo.
- **Suplentes** (`SUPLENTS`): dorsal + nombre completo. Junto al dorsal pueden aparecer iconos (gol, tarjeta) si esa jugadora participó del evento.
- **Cuerpo técnico** (`EQUIP TÈCNIC`): uno o más nombres con un código de rol (`A`, `E`, `D`, `X`, etc.).
- **Tarjetas** (`TARGETES`): si hubo, listado de jugadoras o miembros del cuerpo técnico con color (amarilla/roja, representada con un cuadrito) y minuto.

**Centro del acta**
- **Árbitre** (`ÀRBITRES`): nombre + comité de procedencia entre paréntesis.
- **Goles** (`GOLS`): tabla con marcador parcial creciente (p.ej. `0-1`, `0-2`, ...), autora del gol y minuto. El icono del balón puede variar según equipo y según si es gol en propia puerta.
- **Estadio** (`ESTADI`): nombre + dirección.

**Notas relevantes para la extracción**
- Las tarjetas a entrenadores/delegados ocurren (ver `example3.pdf`).
- Algunas alineaciones tienen jugadoras con un solo nombre (apodo) — no asumir "apellido, nombre" siempre.
- El marcador parcial de la tabla de goles es la fuente de verdad del orden y del autor; `score_home + score_away == len(goals)`.

---

## 3. Restricciones y decisiones arquitectónicas

1. **No usar OCR ni text-extraction de PDF en ningún punto.** El único acceso a las actas es vía **imagen** procesada por el VLM. Esta es la decisión pedagógica central del tutorial.
2. **El stack debe funcionar en Google Colab.** Más adelante el `.py` se trasladará a mano a un `.ipynb` que se ejecutará allí. Implicaciones:
   - **Neo4J: usar AuraDB Free (cloud)**, no Docker. Mismo driver, mismas queries.
   - Dependencias del sistema (`poppler-utils`, `graphviz`) se instalan con `apt-get` desde la celda de bootstrap.
   - Configuración por **funciones importables**, no por CLI obligatoria.
   - Visualizadores devuelven objetos *displayables* (`graphviz.Source`, `IPython.display.IFrame`, etc.) además de escribir archivos en `out/`.
   - Secretos: resolver desde `google.colab.userdata` → `os.environ` → `.env` → `getpass`, en ese orden.
3. **Modelo único**: GPT-4o (OpenAI) tanto como VLM (extracción) como LLM (agente).
4. **Idempotencia**: toda ingesta usa `MERGE`. Re-ejecutar el tutorial no duplica nodos ni gasta tokens innecesarios (extracciones VLM cacheadas en disco).
5. **Determinismo de identidad**: los IDs de entidades (`player_id`, `team_id`, `match_id`) se generan con funciones centralizadas en `src/common/ids.py`. Mismo input → mismo ID, en extractor y en ingestor.
6. **Read-only desde el agente**: el agente puede emitir cualquier Cypher pero la tool `run_cypher` rechaza queries con `CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL` cuando se invoca desde el flujo del agente.
7. **Idioma**: prompts internos en español, respuestas del agente en español, PDFs en catalán (el VLM maneja ambos).

---

## 4. Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| LLM / VLM | OpenAI API, modelo `gpt-4o` |
| Grafo | Neo4J 5 (AuraDB Free para desarrollo y Colab) |
| Driver | `neo4j` (oficial) |
| Validación de schemas | `pydantic` v2 |
| PDF → imagen | `pdf2image` + `poppler-utils` (binario) |
| Visualización ontología | `graphviz` (binario) + binding Python |
| Visualización grafo | `pyvis` |
| Logging | `rich` |
| Reintentos | `tenacity` |
| Carga de config | `python-dotenv` |

Versiones sugeridas en `requirements.txt`:

```
openai>=1.40
neo4j>=5.20
pydantic>=2.7
pdf2image>=1.17
pillow>=10.0
graphviz>=0.20
pyvis>=0.3.2
rich>=13.7
tenacity>=8.2
python-dotenv>=1.0
```

---

## 5. Estructura final del repositorio

```
summer-school/
├── data/
│   ├── examples/           # PDFs (ya existen — no tocar)
│   ├── images/             # PDF→PNG (Stage 2, generado)
│   └── extracted/          # JSONs por partido (Stage 2, generado)
├── out/                    # diagramas, html, trazas (generado)
│   ├── ontology.png
│   ├── ontology.mmd
│   ├── graph.html
│   └── agent_traces/
├── src/
│   ├── __init__.py
│   ├── colab_setup.py             # install_system_deps(), install_python_deps()
│   ├── common/
│   │   ├── __init__.py
│   │   ├── config.py              # resolver de secretos multi-fuente
│   │   ├── paths.py               # ROOT, DATA_DIR, OUT_DIR, ...
│   │   ├── ids.py                 # normalización determinista de IDs
│   │   └── logging.py             # Console rich compartida
│   ├── setup.py                   # check() — health check OpenAI + Neo4J
│   ├── ontology/
│   │   ├── __init__.py
│   │   ├── schema.py              # modelos Pydantic = ontología
│   │   └── visualize.py           # render_ontology() -> graphviz.Source
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── pdf_to_images.py       # convert(pdf_path) -> Path
│   │   ├── vlm_extractor.py       # extract(image_path) -> MatchExtraction
│   │   └── runner.py              # run(force=False), inspect(n)
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── neo4j_client.py        # context-manager + run_read/run_write
│   │   ├── constraints.py         # aplica CREATE CONSTRAINT al primer uso
│   │   ├── ingest.py              # ingest_match(json), ingest_all()
│   │   ├── visualize.py           # render_graph() -> IFrame
│   │   └── schema_intro.py        # graph_schema_summary() -> str
│   └── agent/
│       ├── __init__.py
│       ├── prompts.py             # system prompt + plantillas
│       ├── tools.py               # get_graph_schema, validate_cypher, run_cypher
│       └── agent.py               # ask(question) -> AgentResult
├── tutorial.py                    # wrapper fino: subcomandos all/check/stageN/ask/repl
├── requirements.txt
├── .env.example
├── CLAUDE.md                      # contexto auto-cargado (resumen + reglas)
└── PLAN.md                        # este archivo
```

---

## 6. Convenciones transversales (normativas)

### 6.1 Paths

- `src/common/paths.py` define constantes `ROOT`, `DATA_DIR`, `IMAGES_DIR`, `EXTRACTED_DIR`, `OUT_DIR`, `TRACES_DIR`, todas como `pathlib.Path`.
- `ROOT = Path(__file__).resolve().parents[2]`. Nunca usar paths absolutos hardcodeados ni `os.getcwd()`.
- Las funciones que escriben artefactos hacen `mkdir(parents=True, exist_ok=True)` antes.

### 6.2 IDs y normalización

`src/common/ids.py` expone:

```python
def normalize_name(s: str) -> str: ...
    # 1) NFKD unicode → strip accents
    # 2) upper()
    # 3) collapse whitespace
    # 4) strip

def player_id(full_name: str) -> str:        # "OXLEY SHOVET-HANNAH-MELANY"
def team_id(name: str) -> str:
def stadium_id(name: str) -> str:
def referee_id(name: str) -> str:
def coach_id(full_name: str) -> str:
def match_id(home: str, away: str, journey: int) -> str:
    # f"{team_id(home)}__VS__{team_id(away)}__J{journey}"
def goal_id(match_id: str, idx: int) -> str:
def card_id(match_id: str, idx: int) -> str:
```

**El extractor y el ingestor deben usar estas mismas funciones**, no reimplementar normalización.

### 6.3 Secretos

`src/common/config.py` expone `get_secret(name: str) -> str` con esta cascada:

1. `google.colab.userdata.get(name)` si `google.colab` se puede importar.
2. `os.environ.get(name)`.
3. `dotenv.load_dotenv()` seguido de `os.environ.get(name)`.
4. `getpass.getpass(f"{name}: ")` como fallback interactivo.

Variables requeridas: `OPENAI_API_KEY`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.

### 6.4 Idempotencia

- Todo Cypher de ingesta usa `MERGE` para nodos y `MERGE` para relaciones.
- Re-ejecutar `graph.ingest_all()` dos veces deja los mismos counts.
- La extracción VLM cachea en `data/extracted/example{N}.json`; no se re-llama a la API si el archivo existe, salvo `force=True`.

### 6.5 Seguridad Cypher

- Toda llamada al driver pasa **parámetros**, nunca interpolación de strings con datos del JSON.
- `agent/tools.py::run_cypher` aplica un filtro regex (case-insensitive) que **rechaza** queries que contengan, como tokens, cualquiera de: `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DROP`, `CALL`. Devuelve `{"error": "read-only mode: <token> not allowed"}` sin llegar a Neo4J.
- `ingest.py` y `constraints.py` **no** pasan por esta tool: usan el driver directamente.

### 6.6 Caché

- Imágenes de PDF (`data/images/`): si existen, no reconvertir.
- JSONs extraídos (`data/extracted/`): si existen, no llamar al VLM.
- Banderas `--force` en los subcomandos del `tutorial.py` invalidan las cachés cuando el usuario lo pida.

### 6.7 Visualizadores: doble salida

Toda función `*_visualize` o `render_*` debe:

1. Escribir el artefacto en `out/`.
2. Devolver un objeto renderizable inline en Jupyter:
   - Ontología → `graphviz.Source`.
   - Grafo Neo4J → `IPython.display.IFrame('out/graph.html', width=900, height=600)`.
   - Inspector de extracción → tupla `(IPython.display.Image, dict)`.

### 6.8 Compatibilidad Colab

- `pyvis.network.Network(notebook=True, cdn_resources='in_line')` (obligatorio: CDNs externos pueden estar bloqueados).
- `rich.console.Console(force_terminal=False)`.
- Sin `webbrowser.open()`, sin `os.startfile()`, sin `subprocess` para abrir GUIs.
- Sin hilos ni asyncio salvo lo que ya use `tenacity`.
- Driver Neo4J con `connection_timeout=15` (Aura Free hiberna; mejor fallar rápido).

---

## 7. Etapas

Las etapas se ejecutan en orden. Cada una tiene **Meta**, **Tareas**, **Visualización** y **Criterio de aceptación**. No avanzar a la siguiente etapa sin cumplir el criterio.

---

### Etapa 0 — Bootstrap del entorno

**Meta**: dejar el entorno listo y verificado tanto en local como en Colab.

**Tareas**

1. Crear `requirements.txt` con el contenido de la sección 4.
2. Crear `.env.example` con:
   ```
   OPENAI_API_KEY=sk-...
   NEO4J_URI=neo4j+s://<id>.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=...
   ```
3. Crear `src/common/paths.py`, `src/common/config.py`, `src/common/logging.py` (Console rich global) e `src/common/ids.py` con las funciones de la sección 6.2.
4. Crear `src/colab_setup.py` con:
   - `install_system_deps()`: ejecuta `!apt-get install -y poppler-utils graphviz` (detecta entorno Colab; en local es no-op con aviso).
   - `install_python_deps()`: `!pip install -q -r requirements.txt`.
5. Crear `src/setup.py` con `check() -> bool`:
   - Ping a OpenAI: `client.chat.completions.create(model="gpt-4o", messages=[{"role":"user","content":"ping"}], max_tokens=5)`.
   - Ping a Neo4J: abrir sesión y ejecutar `RETURN 1`.
   - Imprime tabla Rich con resultados y devuelve `True` si ambos OK.
6. Crear `tutorial.py` con `argparse` y subcomando `check` que llame a `setup.check()`. Los demás subcomandos se añaden en cada etapa.

**Visualización**: tabla Rich con dos filas (OpenAI, Neo4J) y estado ✅/❌.

**Aceptación**:
- `python tutorial.py check` muestra ambos en verde.
- Importar `from src import setup; setup.check()` desde un REPL Python funciona igual.

---

### Etapa 1 — Definición de la ontología

**Meta**: declarar la ontología en Pydantic v2 y renderizarla como diagrama.

**Tareas**

1. Crear `src/ontology/schema.py` con los siguientes modelos Pydantic v2. Todos con `model_config = ConfigDict(extra='forbid')` y descripciones (`Field(..., description=...)`) — esas descripciones se usan como pistas para el VLM:

   - `GoalType(StrEnum)`: `regular`, `own`, `penalty`.
   - `CardColor(StrEnum)`: `yellow`, `red`.
   - `LineupRole(StrEnum)`: `starter`, `sub`.
   - `CardTargetKind(StrEnum)`: `player`, `coach`.
   - `Player(BaseModel)`: `name: str`, `jersey: int | None`.
   - `Coach(BaseModel)`: `name: str`, `role_code: str | None`.
   - `LineupEntry(BaseModel)`: `player: Player`, `role: LineupRole`.
   - `Goal(BaseModel)`: `minute: int`, `scoreline_home: int`, `scoreline_away: int`, `scorer_name: str`, `scoring_team: Literal["home","away"]`, `type: GoalType`.
   - `Card(BaseModel)`: `minute: int`, `color: CardColor`, `target_kind: CardTargetKind`, `target_name: str`, `team: Literal["home","away"]`.
   - `Team(BaseModel)`: `name: str`, `lineup: list[LineupEntry]`, `coaches: list[Coach]`.
   - `Stadium(BaseModel)`: `name: str`, `address: str | None`.
   - `Referee(BaseModel)`: `name: str`, `committee: str | None`.
   - `MatchExtraction(BaseModel)`: raíz; `journey: int`, `competition: str`, `status: str`, `score_home: int`, `score_away: int`, `home: Team`, `away: Team`, `stadium: Stadium`, `referee: Referee`, `goals: list[Goal]`, `cards: list[Card]`.

   Importante: la validación en sí no fuerza `len(goals) == score_home + score_away` (eso se verifica fuera, con un warning suave, para no romper el pipeline si la imagen es ambigua).

2. Crear `src/ontology/visualize.py` con:
   ```python
   def render_ontology() -> graphviz.Source: ...
   ```
   Construye el grafo con `graphviz.Digraph`, nodos por cada label, aristas etiquetadas con las relaciones de la sección "Relaciones" más abajo. Renderiza a `out/ontology.png` y devuelve el `Source` para display inline. Adicionalmente, escribe `out/ontology.mmd` con el equivalente Mermaid.

   **Relaciones a representar**:
   - `(Match)-[:HOME_TEAM]->(Team)`
   - `(Match)-[:AWAY_TEAM]->(Team)`
   - `(Match)-[:PLAYED_AT]->(Stadium)`
   - `(Match)-[:OFFICIATED_BY]->(Referee)`
   - `(Match)-[:HAS_GOAL]->(Goal)`
   - `(Match)-[:HAS_CARD]->(Card)`
   - `(Goal)-[:SCORED_BY]->(Player)`
   - `(Goal)-[:FOR_TEAM]->(Team)`
   - `(Card)-[:GIVEN_TO_PLAYER]->(Player)`  (la relación se desdobla por tipo de destinatario para evitar uniones)
   - `(Card)-[:GIVEN_TO_COACH]->(Coach)`
   - `(Card)-[:AGAINST]->(Team)`
   - `(Player)-[:APPEARED_IN {role, jersey}]->(Match)`
   - `(Player)-[:PLAYS_FOR {match_id}]->(Team)`
   - `(Coach)-[:COACHED {match_id}]->(Team)`

3. Añadir subcomando `tutorial.py stage1` que llame a `render_ontology()` y imprima la ruta del PNG.

**Visualización**: `out/ontology.png` + bloque Mermaid en consola (Rich `Syntax` con lexer markdown).

**Aceptación**:
- `out/ontology.png` existe y abre.
- Un fixture sintético (un `MatchExtraction` hardcodeado en `tests/test_schema.py` o en un docstring ejecutable) valida sin errores.

---

### Etapa 2 — Extracción VLM (PDF → JSON, sin OCR)

**Meta**: por cada PDF, generar un JSON validado contra la ontología, usando únicamente la imagen de la página.

**Tareas**

1. Crear `src/extraction/pdf_to_images.py`:
   ```python
   def convert(pdf_path: Path, dpi: int = 220) -> Path: ...
   def convert_all(force: bool = False) -> list[Path]: ...
   ```
   Usa `pdf2image.convert_from_path` (1 página por PDF en nuestros ejemplos). Salida: `data/images/example{N}.png`.

2. Crear `src/extraction/vlm_extractor.py` con la función central:
   ```python
   def extract(image_path: Path) -> MatchExtraction: ...
   ```
   Implementación:
   - Construir prompt sistema (en español) que describa el dominio (sección 2 de este plan), las reglas de interpretación (iconos de gol, propio gol si lo detectas, tarjetas a entrenadores) y exija salida JSON.
   - Llamar `client.chat.completions.create` con:
     - `model="gpt-4o"`
     - `messages=[system, user_with_image]` (la imagen como `image_url` con data URL base64)
     - `response_format={"type":"json_schema","json_schema":{"name":"MatchExtraction","schema":<schema>,"strict":true}}` donde `<schema>` se obtiene de `MatchExtraction.model_json_schema()`.
     - `temperature=0`.
   - Parsear la respuesta con `MatchExtraction.model_validate_json(...)`.
   - Decorar con `@tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(...))` reintentos sobre `ValidationError` y errores de red.

3. Crear `src/extraction/runner.py`:
   ```python
   def run(force: bool = False) -> list[Path]: ...
   def inspect(n: int) -> tuple[Image, dict]: ...
   ```
   - `run` itera `data/examples/example{1,2,3}.pdf` → convierte → extrae → escribe `data/extracted/example{N}.json`. Si el JSON existe y `force=False`, salta.
   - `inspect(n)` carga la imagen y el JSON correspondiente y los devuelve para display.

4. Verificación suave en `runner.run`: tras extraer, comprobar `len(goals) == score_home + score_away` y emitir un `console.log` con warning si no cuadra (no abortar).

5. Subcomando `tutorial.py stage2 [--force] [--inspect N]`.

**Visualización**: `tutorial.py stage2 --inspect 1` muestra dos paneles Rich lado a lado: izquierda metadatos de la imagen, derecha JSON con pretty-print. En notebook, `inspect(1)` devuelve `(Image, dict)` para `display()`.

**Aceptación**:
- `data/extracted/example1.json`, `example2.json`, `example3.json` existen y validan contra `MatchExtraction`.
- Para los 3, `score_home + score_away == len(goals)` (validar manualmente; si algún VLM call no acierta, ajustar el prompt antes de seguir).
- Cada nombre de autora de gol aparece en `home.lineup` ∪ `away.lineup` del equipo correspondiente (`scoring_team`). Tolerar diferencias menores de espacios/comas — comparar con `normalize_name`.

---

### Etapa 3 — Construcción y poblado del grafo Neo4J

**Meta**: a partir de los JSONs, dejar el grafo poblado, consultable, con constraints e índices.

**Tareas**

1. Crear `src/graph/neo4j_client.py`:
   ```python
   class Neo4jClient:
       def __enter__(self): ...
       def __exit__(self, *a): ...
       def run_read(self, cypher: str, **params) -> list[dict]: ...
       def run_write(self, cypher: str, **params) -> list[dict]: ...
   ```
   Driver inicializado con `GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=15)`. Serializa nodos/relaciones a dicts (usar `dict(record)` y `dict(node)` con manejo de `Node`/`Relationship`).

2. Crear `src/graph/constraints.py::apply()` que ejecute (idempotente con `IF NOT EXISTS`):
   ```cypher
   CREATE CONSTRAINT match_id  IF NOT EXISTS FOR (m:Match)   REQUIRE m.id IS UNIQUE;
   CREATE CONSTRAINT team_id   IF NOT EXISTS FOR (t:Team)    REQUIRE t.id IS UNIQUE;
   CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player)  REQUIRE p.id IS UNIQUE;
   CREATE CONSTRAINT coach_id  IF NOT EXISTS FOR (c:Coach)   REQUIRE c.id IS UNIQUE;
   CREATE CONSTRAINT stadium_id IF NOT EXISTS FOR (s:Stadium) REQUIRE s.id IS UNIQUE;
   CREATE CONSTRAINT referee_id IF NOT EXISTS FOR (r:Referee) REQUIRE r.id IS UNIQUE;
   ```

3. Crear `src/graph/ingest.py`:
   ```python
   def ingest_match(data: MatchExtraction) -> None: ...
   def ingest_all() -> dict[str, int]: ...   # devuelve counts por label
   ```
   `ingest_match` debe:
   - Calcular IDs determinísticos con `src/common/ids.py`.
   - `MERGE` para `Match`, `Team` (home y away), `Stadium`, `Referee`.
   - `MERGE` para cada `Player` (de ambas alineaciones) y cada `Coach`.
   - Crear relaciones (`MERGE`):
     - `(Match)-[:HOME_TEAM]->(Team home)`, `(Match)-[:AWAY_TEAM]->(Team away)`.
     - `(Match)-[:PLAYED_AT]->(Stadium)`, `(Match)-[:OFFICIATED_BY]->(Referee)`.
     - Por cada `LineupEntry`: `(Player)-[:APPEARED_IN {role, jersey}]->(Match)` y `(Player)-[:PLAYS_FOR {match_id}]->(Team)`.
     - Por cada `Coach`: `(Coach)-[:COACHED {match_id}]->(Team)`.
     - Por cada `Goal` (indexado por orden): `MERGE (g:Goal {id})`, set propiedades, `(Match)-[:HAS_GOAL]->(g)`, `(g)-[:FOR_TEAM]->(Team)`, y `(g)-[:SCORED_BY]->(Player)` resolviendo `Player` por `normalize_name(scorer_name) == player.id`.
     - Por cada `Card`: análogo, con `GIVEN_TO_PLAYER` o `GIVEN_TO_COACH` según `target_kind`, y `(Card)-[:AGAINST]->(Team)`.
   - Toda parametrizado: el cuerpo del Cypher con `$home_id, $away_id, ...`.

4. Crear `src/graph/visualize.py`:
   ```python
   def render_graph(limit: int = 300) -> IFrame: ...
   ```
   Consulta `MATCH (n)-[r]->(m) RETURN n, r, m LIMIT $limit`, construye una `pyvis.network.Network(notebook=True, cdn_resources='in_line', height='600px', width='100%')`, colorea por label, guarda `out/graph.html`, devuelve `IFrame('out/graph.html', width=900, height=600)`.

5. Crear `src/graph/schema_intro.py`:
   ```python
   def graph_schema_summary() -> str: ...
   ```
   Construye un texto curado que combine:
   - La lista de labels (`CALL db.labels()`).
   - La lista de relationship types (`CALL db.relationshipTypes()`).
   - Una descripción en prosa de la ontología (sección 7-Etapa 1), embebida como string literal (es estable).
   - Ejemplos de Cypher comunes ("para buscar por nombre de jugadora, usa `WHERE p.id = $id` con `id` ya normalizado").
   Esta función la consume el agente.

6. Subcomando `tutorial.py stage3` que:
   - Aplica constraints.
   - Llama `ingest_all()`.
   - Imprime contadores por label.
   - Llama `render_graph()` e imprime la ruta del HTML.

**Visualización**:
- `out/graph.html` (pyvis, autocontenido).
- Tabla Rich con counts por label.
- Mencionar la consola Aura (`console.neo4j.io`) como alternativa interactiva.

**Aceptación**:
- Tras `stage3`, ejecutar `stage3` de nuevo deja los mismos counts (idempotencia).
- Una query manual `MATCH (m:Match) RETURN count(m)` devuelve `3`.
- Una query `MATCH (g:Goal) RETURN count(g)` devuelve la suma de goles de los 3 partidos.

---

### Etapa 4 — Agente NL ↔ Cypher con tool-calling

**Meta**: agente que traduce preguntas en lenguaje natural a Cypher, valida, ejecuta, recupera ante errores y responde parafraseando.

**Tareas**

1. Crear `src/agent/tools.py` con tres funciones puras + descriptores OpenAI:
   ```python
   def get_graph_schema() -> str: ...   # delega en schema_intro.graph_schema_summary

   def validate_cypher(query: str) -> dict:
       # Ejecuta EXPLAIN <query> en Neo4J. Devuelve {"ok": bool, "error": str|None}.
       # No retorna filas. Captura Neo4jError y serializa mensaje.

   def run_cypher(query: str) -> dict:
       # 1. Aplica regex read-only (ver §6.5). Si bloqueado: devuelve {"error": "..."}.
       # 2. Ejecuta en sesión read.
       # 3. Serializa nodos/relaciones a dicts simples.
       # 4. Devuelve {"rows": [...], "error": None} o {"rows": [], "error": "..."}.

   TOOL_SPECS = [...]  # lista de dicts en formato tools de OpenAI (type:"function")
   ```

2. Crear `src/agent/prompts.py` con el system prompt (en español). Debe:
   - Definir el rol: "Asistente que responde preguntas sobre actas de fútbol consultando un grafo Neo4J".
   - Inyectar `get_graph_schema()` al inicio (ya viene del modelo via tool call, pero también lo pre-incluimos en system para acelerar).
   - Reglas explícitas:
     - "Antes de ejecutar, valida tu Cypher con `validate_cypher`".
     - "Para buscar entidades por nombre, normaliza el input con `toUpper` y compara contra la propiedad `id`. Ejemplo: `WHERE p.id CONTAINS toUpper('puiggros')`".
     - "Si una consulta devuelve filas vacías, reformúlala una vez relajando filtros; si sigue vacía, admite honestamente que no encuentras la información".
     - "Nunca inventes labels o propiedades que no estén en el schema".
     - "La respuesta final al usuario debe ser concisa y en español".

3. Crear `src/agent/agent.py`:
   ```python
   @dataclass
   class AgentResult:
       answer: str
       cypher_attempts: list[dict]   # [{"query": str, "ok": bool, "error": str|None, "rows": int}]
       trace_path: Path

   def ask(question: str, max_iterations: int = 5) -> AgentResult: ...
   ```
   Implementación:
   - Inicializa `messages = [system_prompt, user(question)]`.
   - Loop hasta `max_iterations`:
     - `client.chat.completions.create(model="gpt-4o", messages, tools=TOOL_SPECS, tool_choice="auto", temperature=0)`.
     - Si la respuesta tiene `tool_calls`, ejecuta cada uno, añade resultados como mensajes `role="tool"`.
     - Si la respuesta es texto sin tool calls, ese texto es la respuesta final.
   - Persiste el `messages` completo + `cypher_attempts` a `out/agent_traces/{timestamp}.json`.
   - Imprime con Rich: pregunta, cada iteración (con el Cypher resaltado), respuesta final.

4. Subcomandos:
   - `tutorial.py stage4 ask "<pregunta>"`.
   - `tutorial.py repl` → loop `input()` → `ask()` → print.

**Visualización**: panel Rich estructurado por iteración: `[Iter N] Cypher: ... | Result: N rows | Error: ...`. Respuesta final en panel destacado.

**Aceptación**:
- `ask("¿Cuál fue el marcador entre Cirera y L'Estartit?")` responde con `"1-0"` o frase equivalente.
- Al menos una pregunta de la batería de la Etapa 5 dispara un error de Cypher y se recupera (visible en `cypher_attempts`).

---

### Etapa 5 — Orquestador y demostración

**Meta**: ofrecer un único entry point que ejecuta todo en orden y una batería de preguntas de demo.

**Tareas**

1. Completar `tutorial.py` con subcomandos:
   - `check` → `setup.check()`.
   - `stage1` → renderiza ontología.
   - `stage2 [--force] [--inspect N]` → extracción VLM.
   - `stage3` → constraints + ingest + visualización grafo.
   - `stage4 ask "<q>"` → una pregunta puntual.
   - `repl` → bucle interactivo.
   - `demo` → ejecuta las 6 preguntas de demostración listadas abajo, una tras otra, con separadores Rich.
   - `all` → encadena 0→3 y termina con `demo`.

2. **Batería de preguntas de demo** (hardcodeadas en `tutorial.py`):
   1. Lookup directo: *"¿Cuál fue el marcador entre Cirera y L'Estartit?"*
   2. Agregación: *"¿Qué jugadora marcó más goles en la jornada 29?"*
   3. Multi-hop: *"¿En qué estadio jugó el equipo que encajó 6 goles?"*
   4. Filtro temporal: *"Lista los goles marcados antes del minuto 30."*
   5. Honestidad ante grafo incompleto: *"¿Cuántos penaltis se fallaron?"* — el agente debe reconocer que no se modelan penaltis fallados y responderlo.
   6. Aristas mixtas: *"¿Algún entrenador o delegado recibió tarjeta?"* — pone a prueba `GIVEN_TO_COACH`.

**Visualización**: cada pregunta abre con un encabezado Rich (`rule`), la trama del agente, y se cierra con la respuesta final.

**Aceptación**:
- `python tutorial.py demo` ejecuta las 6 preguntas sin crashear.
- Las 6 respuestas son razonables (no necesariamente todas literales, pero coherentes con el grafo).
- Al menos una traza muestra un reintento Cypher exitoso.

---

## 8. Checklist de progreso

Marca cada ítem (con `[x]`) **solo** cuando se cumpla el criterio de aceptación. No avanzar a la siguiente etapa con ítems sin marcar de la anterior.

- [x] **Etapa 0 — Bootstrap**
  - [x] `requirements.txt`, `.env.example`, `tutorial.py` (scaffold) creados.
  - [x] `src/common/{paths,config,ids,logging}.py` implementados.
  - [x] `src/colab_setup.py` con instaladores no-op en local.
  - [x] `src/setup.py::check()` retorna True en local.
  - [x] `python tutorial.py check` muestra ambos ✅.

- [x] **Etapa 1 — Ontología**
  - [x] `src/ontology/schema.py` con todos los modelos Pydantic.
  - [x] `src/ontology/visualize.py::render_ontology()` genera `out/ontology.png` y `out/ontology.mmd`.
  - [x] `python tutorial.py stage1` corre sin errores.
  - [x] Test de validación de un `MatchExtraction` sintético pasa.

- [x] **Etapa 2 — Extracción VLM**
  - [x] `src/extraction/pdf_to_images.py` convierte los 3 PDFs.
  - [x] `src/extraction/vlm_extractor.py::extract()` usa structured outputs.
  - [x] `data/extracted/example{1,2,3}.json` existen y validan.
  - [x] Para cada uno, `len(goals) == score_home + score_away`.
  - [x] Cada `scorer_name` matchea con su `lineup` correspondiente (con normalización).
  - [x] `tutorial.py stage2 --inspect 1` muestra imagen + JSON.

- [x] **Etapa 3 — Grafo Neo4J**
  - [x] `src/graph/neo4j_client.py`, `constraints.py`, `ingest.py` implementados.
  - [x] `ingest_all()` inserta sin error.
  - [x] Segunda ejecución no duplica nodos (counts iguales).
  - [x] `render_graph()` produce `out/graph.html` autocontenido.
  - [x] `graph_schema_summary()` devuelve string usable por el agente.

- [x] **Etapa 4 — Agente**
  - [x] `src/agent/tools.py` con las 3 funciones + filtro read-only operativo.
  - [x] `src/agent/agent.py::ask()` completa el loop con tool-calling.
  - [x] Trazas guardadas en `out/agent_traces/`.
  - [x] Pregunta 1 de demo responde correctamente (1-0 Cirera).

- [x] **Etapa 5 — Orquestador y demo**
  - [x] `tutorial.py demo` subcomando implementado con las 6 preguntas.
  - [x] `tutorial.py demo` ejecuta las 6 preguntas sin crashear.
  - [x] Al menos una traza muestra reintento exitoso tras error (Demo 1: L'Estartit quote fix).
  - [x] `tutorial.py all` corre end-to-end desde cero.

---

## 9. Notas finales para el coding agent

- **Si te reconectas a mitad del proyecto**: lee este PLAN.md completo, mira `CLAUDE.md`, revisa la sección 8 (checklist v1 — legacy) y §14 (checklist v2 — pivot al dataset completo) para saber dónde quedaste, e inspecciona `out/`, `data/extracted/` y `data/extracted_full/` para confirmar artefactos existentes antes de re-ejecutar nada caro.
- **Antes de cada etapa**: confirma que las anteriores cumplen su criterio. Si no, completa lo pendiente primero.
- **Si encuentras ambigüedad en la ontología o en el extractor**: prefiere ser conservador (no inventar tipos, no inferir penaltis si no hay icono claro) y deja una nota en el commit / log.
- **Costes**: una corrida del extractor original son 3 llamadas VLM. La masiva del v2 son 1793; ver §10 para el procedimiento.
- **No introduzcas dependencias extra** sin justificación. Si algo se puede resolver con la stdlib o las libs ya listadas, hazlo así.
- **Commits**: si el repo está bajo git, commits pequeños por etapa con mensajes claros. No hagas commits si no se te ha indicado explícitamente.
- **No crees archivos `.md` adicionales** salvo este `PLAN.md` y `CLAUDE.md`. Cualquier documentación adicional va como docstrings en los módulos.

---

## 10. Pivot al dataset oficial completo (1793 actas) + swap a VLM local

> **Contexto**: el equipo recibió el dataset oficial completo de la FCF, 1793 actas en `data/pages1793/`. El tutorial debe correr sobre datos reales a escala. La extracción se hará **en un servidor GPU con un VLM local** (no GPT-4o) para evitar el coste y la dependencia de OpenAI en la corrida masiva. El notebook que ven los estudiantes en Colab seguirá usando OpenAI sólo para la demo (1-3 actas) y para el agente.

### 10.1 Artefactos y paths

Adiciones a `src/common/paths.py`:

```python
PDFS_FULL_DIR     = DATA_DIR / "pages1793"      # input (commited as untracked dir o entregado aparte)
IMAGES_FULL_DIR   = DATA_DIR / "images_full"    # PNG por PDF, generado por scripts/bulk_convert_pdfs.py
EXTRACTED_FULL_DIR = DATA_DIR / "extracted_full" # JSON por PNG, generado por scripts/bulk_extract.py
```

Convención de nombres: el `stem` del PDF se conserva — `data/pages1793/527.pdf` → `data/images_full/527.png` → `data/extracted_full/527.json`.

### 10.2 Scripts one-off (`scripts/`)

Ambos están escritos para ser **idempotentes y resumibles**. Su contrato:

**`scripts/bulk_convert_pdfs.py`** — sin dependencia de modelo:
- Entrada: `data/pages1793/*.pdf`. Salida: `data/images_full/*.png`.
- Flags: `--dpi 220` (default, igual que el extractor original), `--workers 4`, `--limit N` (smoke test).
- Verifica que cada PDF sea de **1 página**. Si tiene más, se emite warning y se procesa sólo la primera (consistente con el dataset; muestra de 10/1793 confirmó 1 página).
- No requiere GPU; corre en cualquier máquina con `poppler-utils` instalado.

**`scripts/bulk_extract.py`** — corre el VLM:
- Entrada: `data/images_full/*.png`. Salida: `data/extracted_full/<stem>.json`.
- Flag `--provider {openai,local}` (o env `VLM_PROVIDER`):
  - `openai` → delega a `src.extraction.vlm_extractor.extract` (GPT-4o, código existente, intocado).
  - `local` → delega a `src.extraction.vlm_local.extract` (stub; server-Claude lo implementa).
- Flags: `--workers 15` (default — bajar a 1 si es `local`), `--limit N`, `--retry-failures` (relee `_failures.jsonl` y re-procesa solo esos).
- Log de fallos en `data/extracted_full/_failures.jsonl` (JSON-lines, una entrada por fallo con `file`, `error`, `traceback`).
- Soft validations (no bloquean, sólo warning):
  - `len(goals) == score_home + score_away`.
  - Cada `scorer_name` aparece (vía `normalize_name`) en el lineup del equipo que marca.

### 10.3 Procedimiento para el server-Claude (GPU box)

1. **Implementa `src/extraction/vlm_local.py::extract(image_path: Path) -> MatchExtraction`**. El docstring del archivo enumera modelos candidatos (Qwen2-VL-7B-Instruct, InternVL2, Pixtral-12B vía vLLM, LLaVA-NeXT) y la estrategia recomendada de structured output (constrained decoding con Outlines o lm-format-enforcer, o post-hoc validation + self-correction).
2. **Reutiliza el system prompt** existente: `from src.extraction.vlm_extractor import _SYSTEM_PROMPT`. Está afinado sobre los 3 ejemplos en catalán; no lo cambies salvo necesidad documentada.
3. **Corre la conversión** (no necesita modelo): `python scripts/bulk_convert_pdfs.py`. Tiempo estimado: 10–30 min según CPU.
4. **Corre la extracción**: `python scripts/bulk_extract.py --provider local --workers 1`. Tiempo estimado: depende del modelo y la VRAM. Si se interrumpe, re-ejecutar continúa desde donde quedó.
5. **Procesa fallos** (si los hay): inspecciona `_failures.jsonl`. Si son ambigüedades genuinas del documento, déjalos así. Si son bugs del backend, fíxa el backend y `python scripts/bulk_extract.py --provider local --retry-failures`.
6. **Comprime y entrega** dos zips separados:
   - `images_full.zip` (carpeta `data/images_full/`).
   - `extracted_full.zip` (carpeta `data/extracted_full/`, **excluyendo** `_failures.jsonl` antes de subir).
7. **No toques** el notebook ni `vlm_extractor.py`. El rewire del notebook se hace después, con los IDs de GDrive que devuelva el usuario.

### 10.4 Coste y tiempo (referencia, si se usara OpenAI)

- ~5500 tokens input + ~800 tokens output por acta a 220 DPI con detail=high.
- $0.022/acta × 1793 ≈ **$40 USD totales**.
- 15 workers concurrentes ≈ **45 min** corridos.
- Se documenta para tener referencia; **la corrida real es con VLM local**.

---

## 11. Refactor del notebook canónico

> **Goal**: cuando el usuario tenga los GDrive IDs de `images_full.zip` y `extracted_full.zip`, modificar `summer_school_document_agentic_rag_tutorial.ipynb` para que (a) descargue ambos zips al **inicio** del notebook, (b) salte la extracción VLM masiva (ya está hecha), (c) reformule la narrativa para que los estudiantes entiendan que partimos de artefactos pre-computados pero podemos ver la extracción en vivo sobre 1-2 muestras.

### 11.1 Estado pre-rewire

Estructura actual del notebook (61 celdas):

- 0–2: header + diagrama mermaid + intro.
- 3–8: credentials + env setup + connectivity check.
- 9–10: **Mid-notebook PDF download** (`gdown` el ID `10i1tmcyK02hulmpBgWUdUzULwqWz1mzC`, unzip a `data/documents/`). Esto es lo que hay que reemplazar.
- 11–17: ontología (schema + viz).
- 18–23: extracción VLM (`convert_all`, `run()` — corre sobre `data/documents/example*.pdf`).
- 24–29: inspección de resultados + quality checks.
- 30–39: ingesta al grafo + viz + idempotency.
- 40–59: agente + demos.
- 60: conclusión.

### 11.2 Estructura post-rewire

Cambios concretos:

1. **Reemplazar cell 10** (mid-notebook PDF download) por una celda movida al inicio que descargue PNG zip y JSON zip. La narrativa nueva: "ya hemos pre-procesado las 1793 actas; ahora descargamos los artefactos y nos enfocamos en la parte interesante".
2. **Insertar la celda agrupada de downloads inmediatamente después del connectivity check** (cell 8) — ANTES de la sección de ontología, para tener todo lo necesario disponible.
3. **Modificar el código de las celdas 18–23 (Stage 2 - VLM)**: en vez de correr `run()` sobre los 3 ejemplos, hacer una demo en vivo sobre **1-2 PNGs del dataset masivo** usando `extract()` (OpenAI, barato, ilustrativo). El resto se muestra como "ya está extraído, aquí están los 1793 JSONs".
4. **Modificar las celdas 30–37 (Stage 3 - graph)**: ingestar desde `EXTRACTED_FULL_DIR` en lugar de `EXTRACTED_DIR`. Ajustar `src/graph/ingest.py::ingest_all()` para aceptar un parámetro de directorio (o agregar `ingest_full()` que itera sobre `EXTRACTED_FULL_DIR`).
5. **Ajustar las preguntas del agente (40–59)**: las 6 preguntas actuales son específicas a los 3 ejemplos ("Cirera vs L'Estartit"). Con 1793 actas, hay que (a) reformular preguntas que aprovechen la escala — "¿qué equipo ganó más partidos en la jornada N?", "¿cuántos goles marcó X jugadora en toda la temporada?", o (b) mantener algunas específicas a equipos conocidos del dataset y agregar agregaciones nuevas. Esta lista de preguntas se diseña con el usuario antes de implementar.

### 11.3 Implementación práctica

Pseudo-código de la celda de descargas consolidada:

```python
# === Consolidated downloads (one-time, idempotent) ===
PNG_ZIP_GDRIVE_ID  = "<placeholder>"  # filled in once usuario sube
JSON_ZIP_GDRIVE_ID = "<placeholder>"

from src.common.paths import IMAGES_FULL_DIR, EXTRACTED_FULL_DIR
import subprocess, os, zipfile
from pathlib import Path

def _download_and_unzip(gdrive_id: str, target_dir: Path, label: str):
    target_dir.mkdir(parents=True, exist_ok=True)
    # Skip if there's already enough content
    if any(target_dir.iterdir()):
        print(f"  {label}: already populated, skipping download.")
        return
    zip_path = f"{label}.zip"
    subprocess.run(["gdown", f"https://drive.google.com/uc?id={gdrive_id}", "-O", zip_path], check=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target_dir)
    os.remove(zip_path)
    print(f"  {label}: downloaded and unpacked.")

_download_and_unzip(PNG_ZIP_GDRIVE_ID,  IMAGES_FULL_DIR,    "images_full")
_download_and_unzip(JSON_ZIP_GDRIVE_ID, EXTRACTED_FULL_DIR, "extracted_full")
```

### 11.4 Criterio de aceptación

- El notebook abre en Colab, ejecuta sin error de top a bottom.
- Sólo se hacen 2 llamadas a OpenAI (la demo de extracción) + las del agente.
- El grafo ingesta los ~1793 partidos en menos de 5 min (estimar tras la primera corrida — ajustar batch size de Cypher si hace falta).
- Las preguntas demo del agente devuelven respuestas no-triviales (no "no encontré información").

---

## 12. Split del tutorial en Part 1 (laboratorio) + Part 2 (operacional)

> **Motivación del equipo**: el tutorial actual es robusto pero los estudiantes pierden la sensación de "estamos construyendo esto". Se quiere una primera parte donde toquen cosas en ambiente controlado, vean el sistema por dentro, modifiquen pequeñas piezas, y entiendan cada componente. La segunda parte muestra el sistema operando a escala con el dataset oficial.

### 12.1 Decisiones

- **Dataset Part 1**: los 3 `example*.pdf` ya en `data/documents/` (PNGs en `data/images/`, JSONs en `data/extracted/`). Ya están ingestados, validados, son **suficientes** para mostrar todo el flujo y los estudiantes pueden "romperlos" sin riesgo.
- **Dataset Part 2**: las 1793 actas desde GDrive como precomputed PNG+JSON (ver §10 y §11).
- **Archivos**:
  - Part 1 → `summer_school_part1_lab.ipynb` (nuevo).
  - Part 2 → `summer_school_document_agentic_rag_tutorial.ipynb` (existente, post-rewire §11).
- **Continuidad narrativa**: Part 1 cierra con "ahora que entiendes los componentes, veamos cómo escala", linkeando a Part 2.

### 12.2 Estructura propuesta de Part 1 (lab)

| Sección | Contenido | TODO del estudiante |
|---|---|---|
| **0. Setup** | Credenciales + env. Idéntico a Part 2. | (ninguno — sólo pegar credenciales) |
| **1. El dominio** | Vista preview de 1 PDF de muestra (`example1.pdf`). Lectura del PDF y explicación de qué información extraer. | (lectura guiada) |
| **2. Ontología — workshop** | Mostrar `MatchExtraction` con todos sus campos. Diagrama graphviz. | **TODO**: agregar un campo opcional `position: str \| None` al `Player` y regenerar el diagrama. Validación: el `MatchExtraction` sintético del notebook sigue validando. |
| **3. VLM en vivo** | Corre `extract()` sobre 1 PDF (visible). Muestra el system prompt. Compara JSON con el PDF lado a lado. | **TODO**: modificar UNA línea del system prompt (sugerencia: añadir "be conservative with own goals — only mark type='own' if explicitly shown") y re-extraer. Comparar JSON antes/después. |
| **4. Grafo — workshop** | Mostrar `ingest_match` paso a paso (constraints, MERGE, relationships). | **TODO**: escribir una query Cypher (con plantilla guía) que cuente goles por equipo, ejecutarla con `run_cypher`. Validación: el resultado coincide con el agregado calculado en Python desde los JSONs. |
| **5. Agente — workshop** | Mostrar `ask()` con la pregunta 1 de la batería original ("Cirera vs L'Estartit"). Mostrar la traza completa. | **TODO**: modificar UNA línea del system prompt del agente (sugerencia: tono más formal o más casual), preguntar de nuevo, observar el cambio. |
| **6. Conclusión & transición** | Recap. "En Part 2 verás esto mismo correr sobre 1793 actas." | — |

### 12.3 Guardrails pedagógicos

Cada celda de TODO debe ir seguida de una celda de validación que diga:

- ✅ "Tu cambio preserva el invariante X" (con explicación de por qué).
- ❌ "Tu cambio rompió el invariante Y — aquí está la diferencia (diff)".

Esto reduce frustración cuando los estudiantes experimentan.

### 12.4 Implementación

Cuando llegue el momento (después de §11):

1. **Copia el notebook canónico** post-rewire a `summer_school_part1_lab.ipynb`.
2. **Elimina** las secciones de download masivo, Stage 2 demo a escala, las 6 preguntas avanzadas. Mantén la batería original de 6 preguntas adaptada para los 3 ejemplos.
3. **Inserta las celdas de TODO** con bloque markdown destacado ("📝 Tu turno") y la celda de validación inmediatamente después.
4. **Marca claramente** las áreas que NO se deben modificar (el resto del notebook) — con un disclaimer al inicio.
5. **Revisa el orden**: ontología → extracción → grafo → agente, con cada sección autónoma (un estudiante puede saltar la extracción si no quiere gastar tokens).
6. **Confirma con el usuario** los TODOs específicos antes de escribirlos definitivamente.

### 12.5 Criterio de aceptación

- `summer_school_part1_lab.ipynb` corre completo en Colab sin error.
- Cada TODO tiene una solución que pasa la validación inmediata.
- El notebook no tarda más de **15 min** end-to-end (Part 2 puede tardar 30+ min con la ingesta masiva).
- Los TODOs son **reversibles** (`reset_to_default()` o re-clone del repo basta).

---

## 13. Estado de los notebooks

- `tutorial.ipynb` (62 celdas) — versión antigua, **no es el canónico**. Probablemente se puede borrar tras el split. Confirmar con el usuario antes.
- `summer_school_document_agentic_rag_tutorial.ipynb` (61 celdas) — **canónico actual**, va a convertirse en Part 2 tras §11.
- `summer_school_part1_lab.ipynb` — **pendiente de crear** (§12).

---

## 14. Checklist v2 — Pivot al dataset completo + split

Marca cada ítem con `[x]` sólo cuando se cumpla.

- [x] **§10.1 Paths**: `PDFS_FULL_DIR`, `IMAGES_FULL_DIR`, `EXTRACTED_FULL_DIR` añadidos a `src/common/paths.py`.
- [x] **§10.2 Scripts**: `scripts/bulk_convert_pdfs.py` y `scripts/bulk_extract.py` creados, con `--help` funcional.
- [x] **§10.3 Stub**: `src/extraction/vlm_local.py` creado con docstring de contrato y `NotImplementedError`.
- [x] **§10.3 Local backend implementado** (server-Claude): `src/extraction/vlm_local.py::extract()` con `Qwen/Qwen3-VL-8B-Instruct` vía `transformers.AutoModelForImageTextToText`. Singleton lazy-load, self-correction loop sobre `ValidationError`. Outputs en `data/extracted_full/<model-tag>/` (model-namespaced).
- [x] **§10.3 Multi-GPU orchestrator**: `scripts/bulk_extract_local.py` detecta GPUs libres por umbral de memoria (`nvidia-smi`), reparte el dataset en shards (1 worker por GPU vía `CUDA_VISIBLE_DEVICES` + `CUDA_DEVICE_ORDER=PCI_BUS_ID`), agrega fallos. `scripts/bulk_extract.py` ahora acepta `--shard I/N` y `--model-tag`. Lanzar siempre con `setsid nohup ... < /dev/null > log 2>&1 &` para que sobreviva al cierre de Claude/SSH (ver CLAUDE.md §Handoff).
- [x] **§10.3 PNGs masivos**: `data/images_full/*.png` (1793 archivos) generados con `bulk_convert_pdfs.py`.
- [x] **§10.3 JSONs masivos**: RE-EXTRACCIÓN COMPLETA (669 min, GPUs 1,2,4,5) con prompt corregido. **1793/1793 JSONs**, todos parsean y validan. Primer full run (543 min) tenía **defecto sistemático**: Qwen3-VL omitía la sección SUPLENTS en el 92% de los team-sides (vs. 2–8 subs/equipo con GPT-4o). Causa raíz confirmada por probe A/B sobre `10.png`: prompt actual → 0 subs; prompt con énfasis explícito en SUPLENTS → 9+7 subs (coincide con la imagen). Fix aplicado en `src/extraction/vlm_local.py` (`_SUPLENTS_EMPHASIS` apéndice a `_SYSTEM_PROMPT`, **sin tocar `vlm_extractor.py`**). **Validación post-run (new vs backup) sobre 3584 team-sides**: zero-sub 7.3% (era 91.9%), avg subs 4.6 (era 0.3), scorer-miss 3.1% (era 16.4%), starters 10.4/side sin regresión, goal-mismatch 1.6% (≈ igual). Residuales (zero-sub 7%, goal-mismatch 1.6%, scorer-miss 3%) son extracciones FIELES de actas futbol-7/blancas/sparse/own-goals, NO errores de modelo — NO investigadas a fondo. `75.png` falló por trailing-comma reproducible del modelo → fix `_repair_trailing_commas()` (salvage solo en ValidationError) en `vlm_local.py`; reextraído OK. Backup del run anterior en `data/extracted_full/qwen3-vl-8b-instruct__gpt-prompt-backup/` (1793 JSONs, **borrable** — nuevo run validado).
- [x] **§10.3 Zips entregados**: `out/images_full.zip` (504M, 1793 PNG) y `out/extracted_full.zip` (2.4M, 1793 JSON, sin `_worker_logs`/`_failures.jsonl`) listos para subir a GDrive.
- [x] **§11 GDrive IDs** (verificados públicos, 2026-05-24):
  - `images_full.zip`  (504M, 1793 PNG)  → GDrive ID `1FSBFc6nijVjApTh4YoP0seI8lOpBL6Xc`
  - `extracted_full.zip` (2.4M, 1793 JSON) → GDrive ID `1GWH8lCd7TQV8g6N16intWJ5AFhpCU0FX`
  - En §11.3: `PNG_ZIP_GDRIVE_ID = "1FSBFc6nijVjApTh4YoP0seI8lOpBL6Xc"`, `JSON_ZIP_GDRIVE_ID = "1GWH8lCd7TQV8g6N16intWJ5AFhpCU0FX"`.
- [ ] **§11.3 Notebook rewire**: descargas consolidadas al inicio, demo VLM reducida, ingesta apunta a `EXTRACTED_FULL_DIR`, preguntas del agente actualizadas.
- [ ] **§11.4 Aceptación rewire**: notebook corre end-to-end en Colab sin error, ≤5 llamadas OpenAI fuera del agente.
- [ ] **§12 TODOs Part 1 confirmados** con el usuario (los 4 propuestos en §12.2 o variantes).
- [ ] **§12.4 Part 1 creado**: `summer_school_part1_lab.ipynb` con TODOs + validaciones.
- [ ] **§12.5 Aceptación split**: Part 1 corre sin error en Colab en ≤15 min, cada TODO tiene solución que valida.
