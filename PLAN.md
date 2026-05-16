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

- [ ] **Etapa 0 — Bootstrap**
  - [ ] `requirements.txt`, `.env.example`, `tutorial.py` (scaffold) creados.
  - [ ] `src/common/{paths,config,ids,logging}.py` implementados.
  - [ ] `src/colab_setup.py` con instaladores no-op en local.
  - [ ] `src/setup.py::check()` retorna True en local.
  - [ ] `python tutorial.py check` muestra ambos ✅.

- [ ] **Etapa 1 — Ontología**
  - [ ] `src/ontology/schema.py` con todos los modelos Pydantic.
  - [ ] `src/ontology/visualize.py::render_ontology()` genera `out/ontology.png` y `out/ontology.mmd`.
  - [ ] `python tutorial.py stage1` corre sin errores.
  - [ ] Test de validación de un `MatchExtraction` sintético pasa.

- [ ] **Etapa 2 — Extracción VLM**
  - [ ] `src/extraction/pdf_to_images.py` convierte los 3 PDFs.
  - [ ] `src/extraction/vlm_extractor.py::extract()` usa structured outputs.
  - [ ] `data/extracted/example{1,2,3}.json` existen y validan.
  - [ ] Para cada uno, `len(goals) == score_home + score_away`.
  - [ ] Cada `scorer_name` matchea con su `lineup` correspondiente (con normalización).
  - [ ] `tutorial.py stage2 --inspect 1` muestra imagen + JSON.

- [ ] **Etapa 3 — Grafo Neo4J**
  - [ ] `src/graph/neo4j_client.py`, `constraints.py`, `ingest.py` implementados.
  - [ ] `ingest_all()` inserta sin error.
  - [ ] Segunda ejecución no duplica nodos (counts iguales).
  - [ ] `render_graph()` produce `out/graph.html` autocontenido.
  - [ ] `graph_schema_summary()` devuelve string usable por el agente.

- [ ] **Etapa 4 — Agente**
  - [ ] `src/agent/tools.py` con las 3 funciones + filtro read-only operativo.
  - [ ] `src/agent/agent.py::ask()` completa el loop con tool-calling.
  - [ ] Trazas guardadas en `out/agent_traces/`.
  - [ ] Pregunta 1 de demo responde correctamente.

- [ ] **Etapa 5 — Orquestador y demo**
  - [ ] `tutorial.py demo` ejecuta las 6 preguntas sin crashear.
  - [ ] Al menos una traza muestra reintento exitoso tras error.
  - [ ] `tutorial.py all` corre end-to-end desde cero.

---

## 9. Notas finales para el coding agent

- **Si te reconectas a mitad del proyecto**: lee este PLAN.md completo, mira `CLAUDE.md`, revisa la sección 8 (checklist) para saber dónde quedaste, e inspecciona `out/` y `data/extracted/` para confirmar artefactos existentes antes de re-ejecutar nada caro (extracción VLM).
- **Antes de cada etapa**: confirma que las anteriores cumplen su criterio. Si no, completa lo pendiente primero.
- **Si encuentras ambigüedad en la ontología o en el extractor**: prefiere ser conservador (no inventar tipos, no inferir penaltis si no hay icono claro) y deja una nota en el commit / log.
- **Costes**: una corrida completa de extracción son ~3 llamadas VLM. Cachear es obligatorio. La demo del agente son ~6 conversaciones, cada una con 2-5 iteraciones; presupuesto manejable.
- **No introduzcas dependencias extra** sin justificación. Si algo se puede resolver con la stdlib o las libs ya listadas, hazlo así.
- **Commits**: si el repo está bajo git, commits pequeños por etapa con mensajes claros (`stage 0: bootstrap`, `stage 1: ontology + viz`, etc.). No hagas commits si no se te ha indicado explícitamente.
- **No crees archivos `.md` adicionales** salvo este `PLAN.md` y `CLAUDE.md`. Cualquier documentación adicional va como docstrings en los módulos.
