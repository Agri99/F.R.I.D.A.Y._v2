F.R.I.D.A.Y. v2
SearXNG Search + Speech Director / Chatterbox Turbo
Full Implementation Run Book
Repository baseline: Agri99/F.R.I.D.A.Y._v2 (main) | Prepared 2026-09-27
Purpose: provide an exact, executable change plan for replacing direct DuckDuckGo search integration with a self-hosted SearXNG service and adding a dedicated Speech Director between every language-model output path and Chatterbox Turbo TTS.
Scope: this run book is written against the current repository structure and current file contents inspected from the main branch. It intentionally preserves the existing Qwen/Gemini brain router and Chatterbox Turbo model instead of introducing a second LLM or second TTS model.
Important implementation rule: do not fine-tune Qwen or Gemini for emotion in this first implementation. The first cutover is a deterministic Speech Director with empirical Chatterbox tag calibration. A learned Speech Director can be considered later after evaluation data exists.

## 1. Target State
```text
User
```
```text
  |
```
```text
  +--> Brain Router
```
```text
  |      +--> Qwen2.5 1.5B (fast)
```
```text
  |      +--> Qwen3 8B (reasoning)
```
```text
  |      +--> Gemini cloud brain
```
```text
  |
```
```text
  +--> Online tools
```
```text
  |      +--> SearXNG (self-hosted, general web search)
```
```text
  |      +--> Wikipedia (specialized fallback)
```
```text
  |      +--> Google News RSS (specialized news fallback)
```
```text
  |
```
```text
  +--> Response text
```
```text
          |
```
```text
          +--> Speech Director
```
```text
                 +--> emotion
```
```text
                 +--> intensity
```
```text
                 +--> delivery
```
```text
                 +--> tag selection
```
```text
                 +--> final TTS text (private)
```
```text
                          |
```
```text
                          +--> Chatterbox Turbo
```
```text
                                  |
```
```text
                                  +--> Audio playback
```
SearXNG is the general-purpose search layer. Wikipedia and Google News remain specialized sources because the existing project already uses them and they serve distinct retrieval roles. FRIDAY itself no longer makes direct DuckDuckGo API/HTML requests.
The Speech Director is not another conversational brain. It decides how already-generated text should be spoken. User-visible text remains clean; Chatterbox-specific tags are injected only at the TTS boundary.

## 2. Current Repository Baseline
| Area | Current state | Run book consequence |
| --- | --- | --- |
| Search provider | `src/friday/online/search.py` contains Wikipedia, Google News, DuckDuckGo Instant Answer API, and DuckDuckGo Lite HTML fallback. | Replace only the DDG tiers; make SearXNG primary. Keep Wikipedia and Google News as specialized fallback layers. |
| Search tool | `src/friday/tools/online.py` creates `WebSearchProvider()` globally with no configuration injection. | Change registration to receive `settings` and construct the provider from `settings.search`. |
| Source registry | `src/friday/online/sources.py` labels search as DuckDuckGo. | Change the search source entry to SearXNG. |
| Config model | `src/friday/config.py` has no `SearchConfig` or Speech Director configuration model. | Add structured Pydantic config sections. |
| Local voice path | `app.py` builds `SpeechSynthesizer`, then an event-driven `VoicePipeline` and `VoiceSession`. | Inject one Speech Director into `VoiceSession`; the pipeline itself stays focused on streaming. |
| Gemini Live path | `src/friday/interaction/gemini_live.py` queues response sentences directly for Chatterbox. | Inject the same Speech Director and render each sentence before enqueueing. |
| TTS | `src/friday/interaction/tts.py` is already Chatterbox Turbo and preserves bracketed tags. | Keep the engine and model. Refine tag handling and document experimental vs verified tags. |
| Streaming TTS docs | `pipeline.py` and `streaming_tts.py` still contain stale Piper wording. | Update comments/docstrings to Chatterbox Turbo. |
| Repo artifacts | Root `ddg.html` and `ddg_lite.html` are present. | Delete after a reference scan confirms they are diagnostic leftovers. |
| Dependencies | `requests` and `beautifulsoup4` already exist in `requirements.txt`; Chatterbox is already installed through the voice stack. | No new Python search package and no new TTS model are required. |



## 3. Exact Downloads / External Components
Only these external components are required for the first cutover. SearXNG is containerized; its dependent Valkey service is pulled automatically by the official Compose template.
| Item | Required? | Exact source / artifact | Where it goes | Reason |
| --- | --- | --- | --- | --- |
| Docker Desktop for Windows | Only if Docker Desktop is not already installed | Official Docker Desktop download/install page | Host OS; not committed to repo | Runs the local Linux containers used by SearXNG. |
| SearXNG Compose template | Yes | https://raw.githubusercontent.com/searxng/searxng/master/container/docker-compose.yml | `ops/searxng/docker-compose.yml` | Official container deployment template. |
| SearXNG environment template | Yes | https://raw.githubusercontent.com/searxng/searxng/master/container/.env.example | `ops/searxng/.env.example` | Official template for version/host/port settings. |
| SearXNG model weights | No | None | N/A | SearXNG is a search service; it does not require a local ML model. |
| Additional LLM | No | None | N/A | Speech Director is deterministic in v1. |
| Additional TTS model | No | None | N/A | Continue using `chatterbox-tts` and `models/chatterbox-turbo`. |
| New Python search library | No | None | N/A | Use existing `requests`. |


Official SearXNG documentation recommends Compose as the container deployment route and documents the `/search` JSON API. The JSON format must be enabled in the instance settings, otherwise a JSON request can be rejected with HTTP 403.

## 4. Phase 0 - Freeze and Backup Before Editing
1. Open a clean PowerShell in the repository root.
```text
cd C:\Dev\F.R.I.D.A.Y._v2
```

```text
git status --short
```
```text
git branch --show-current
```
```text
git rev-parse HEAD
```
2. Create a safety branch. Use your own branch name if you already have a branching convention.
```text
git switch -c feat/searxng-speech-director
```
3. Create a local archive of the current state. Do not delete the SQLite database, voice reference, or model directory.
```text
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
```
```text
New-Item -ItemType Directory -Force -Path "backups\$stamp" | Out-Null
```
```text
git archive --format=zip --output "backups\$stampriday-pre-searxng-speech-director.zip" HEAD
```
4. Record the currently installed Python packages so dependency drift can be detected later.
```text
python -m pip freeze > "backups\$stamp\pip-freeze-pre.txt"
```
5. Run the existing baseline tests. Do not start modifications until the baseline is known.
```text
pytest tests/ -q
```
If baseline tests fail before this work, record the failures separately. Do not silently attribute pre-existing failures to SearXNG or Speech Director changes.

## 5. Phase 1 - Deploy SearXNG Locally

### 5.1 Create the deployment directory
```text
cd C:\Dev\F.R.I.D.A.Y._v2
```
```text
New-Item -ItemType Directory -Force -Path "ops\searxng\core-config" | Out-Null
```
```text
Set-Location "ops\searxng"
```

### 5.2 Download the official templates
```text
Invoke-WebRequest `
```
```text
  -Uri "https://raw.githubusercontent.com/searxng/searxng/master/container/docker-compose.yml" `
```
```text
  -OutFile "docker-compose.yml"
```

```text
Invoke-WebRequest `
```
```text
  -Uri "https://raw.githubusercontent.com/searxng/searxng/master/container/.env.example" `
```
```text
  -OutFile ".env.example"
```

```text
Copy-Item ".env.example" ".env"
```
Do not hand-write the Compose file in v1. Start from the official template so the SearXNG and Valkey service definitions track upstream.

### 5.3 Edit `.env`
Replace the relevant values so the service is reachable only from the local machine and uses a predictable port.
```text
SEARXNG_VERSION=latest
```
```text
SEARXNG_HOST=127.0.0.1
```
```text
SEARXNG_PORT=8080
```
Add a random secret. This secret should not be committed. Generate one with:
```text
$secret = python -c "import secrets; print(secrets.token_hex(32))"
```
```text
Add-Content -Path ".env" -Value "SEARXNG_SECRET=$secret"
```
After editing, `.env` must be ignored by git. Check the repo `.gitignore`; if `ops/searxng/.env` is not covered, add that exact path.

### 5.4 Create `core-config/settings.yml`
Create exactly this minimal custom configuration. The important part is enabling JSON output for the FRIDAY client. Keep the default engines initially; tune engine selection only after the first baseline passes.
```text
use_default_settings: true
```

```text
general:
```
```text
  instance_name: "FRIDAY SearXNG"
```
```text
  debug: false
```

```text
search:
```
```text
  default_lang: "en"
```
```text
  safe_search: 1
```
```text
  formats:
```
```text
    - html
```
```text
    - json
```

```text
server:
```
```text
  limiter: false
```
Do not put `SEARXNG_SECRET` into `settings.yml`. Let the official container environment override the server secret.

### 5.5 Start and verify SearXNG
```text
docker compose pull
```
```text
docker compose up -d
```
```text
docker compose ps
```
Then test the JSON API directly from PowerShell:
```text
Invoke-RestMethod `
```
```text
  -Uri "http://127.0.0.1:8080/search?q=python+django&format=json" | `
```
```text
  Select-Object -ExpandProperty results | `
```
```text
  Select-Object -First 3
```
Expected result: a JSON object containing a `results` list with fields such as title, URL, and content/snippet. If you receive HTTP 403, verify `search.formats` contains `json`, then restart the service.

### 5.6 SearXNG operational commands
```text
# Status
```
```text
docker compose ps
```

```text
# Live logs
```
```text
docker compose logs -f core
```

```text
# Restart after config changes
```
```text
docker compose up -d
```

```text
# Stop
```
```text
docker compose down
```

```text
# Pull updated images later
```
```text
docker compose pull
```
```text
docker compose up -d
```

## 6. Phase 2 - Modify Search Integration

### 6.1 `src/friday/config.py` - ADD two config models
Add a `SearchConfig` model and a `SpeechDirectorConfig` model. Add both to `FridayConfig`; attach Speech Director config under `VoiceConfig` so all voice transports share it.
```text
class SearchConfig(BaseModel):
```
```text
    enabled: bool = True
```
```text
    base_url: str = "http://127.0.0.1:8080"
```
```text
    timeout_seconds: float = 6.0
```
```text
    max_results: int = 5
```
```text
    language: str = "en"
```
```text
    safe_search: int = 1
```
```text
    specialized_fallbacks: bool = True
```

```text
class SpeechDirectorConfig(BaseModel):
```
```text
    enabled: bool = True
```
```text
    mode: str = "rules"
```
```text
    max_tags_per_sentence: int = 1
```
```text
    allow_vocal_effects: bool = True
```
```text
    allow_experimental_emotion_tags: bool = False
```
```text
    log_decisions: bool = False
```
Then add:
```text
class VoiceConfig(BaseModel):
```
```text
    ...
```
```text
    speech_director: SpeechDirectorConfig = Field(default_factory=SpeechDirectorConfig)
```

```text
class FridayConfig(BaseModel):
```
```text
    ...
```
```text
    search: SearchConfig = Field(default_factory=SearchConfig)
```
Do not remove any existing configuration fields. Preserve backward compatibility for existing YAML files by giving new fields defaults.

### 6.2 `config/default.yaml` - ADD configuration
Add a top-level `search:` section and a nested `voice.speech_director:` section. Do not change the existing Qwen model values, voice model path, device, or exaggeration during this phase.
```text
search:
```
```text
  enabled: true
```
```text
  base_url: "http://127.0.0.1:8080"
```
```text
  timeout_seconds: 6
```
```text
  max_results: 5
```
```text
  language: "en"
```
```text
  safe_search: 1
```
```text
  specialized_fallbacks: true
```

```text
voice:
```
```text
  speech_director:
```
```text
    enabled: true
```
```text
    mode: "rules"
```
```text
    max_tags_per_sentence: 1
```
```text
    allow_vocal_effects: true
```
```text
    allow_experimental_emotion_tags: false
```
```text
    log_decisions: false
```
Keep `config/gemini.yaml` unchanged for this first cutover unless you specifically want a Gemini-only override. `FridayConfig` defaults will supply the same SearXNG and Speech Director settings in the overlay configuration.

### 6.3 `src/friday/online/search.py` - REPLACE the DDG tiers
Preserve the public `WebSearchProvider.search(query, max_results)` API so the rest of FRIDAY does not need to know the provider changed.
The new implementation should have this exact responsibility split:
| Layer | Action | Keep / Remove |
| --- | --- | --- |
| Primary | GET `http://127.0.0.1:8080/search` with `q`, `format=json`, `language`, `safesearch`. | ADD SearXNG. |
| Specialized fallback 1 | Wikipedia API + summary extraction. | KEEP. |
| Specialized fallback 2 | Google News RSS. | KEEP. |
| Direct DDG API | `https://api.duckduckgo.com/`. | REMOVE. |
| DDG Lite | `https://lite.duckduckgo.com/lite/`. | REMOVE. |
| Compatibility alias | `DuckDuckGoScraper = WebSearchProvider`. | REMOVE after repo reference scan; no internal caller should need it. |


Recommended internal classes/functions: `SearchResult` stays unchanged; add a small `SearXNGProvider` helper or keep SearXNG logic inside `WebSearchProvider`. The latter is the lower-risk change because `tools/online.py` already expects `WebSearchProvider`.
The SearXNG parser should tolerate missing `content`, missing `title`, duplicate URLs, non-200 responses, connection errors, and malformed JSON. Never let a search failure crash the voice session; return the same empty/error semantics the existing tool layer expects.

### 6.4 `src/friday/online/sources.py` - MODIFY search registration
Change only the search capability entry:
```text
"search": CapabilitySource(
```
```text
    name="SearXNG",
```
```text
    primary_url="http://127.0.0.1:8080/search",
```
```text
    fallback_strategy="wikipedia_then_google_news",
```
```text
    requires_auth=False,
```
```text
),
```

### 6.5 `src/friday/tools/online.py` - MODIFY provider construction
Remove the global `scraper = WebSearchProvider()` assumption. Pass configuration into the registration function while keeping the old one-argument form valid for tests or external callers.
```text
def register_all_tools(registry, settings=None) -> None:
```
```text
    ...
```
```text
    search_cfg = getattr(settings, "search", None) if settings is not None else None
```
```text
    scraper = WebSearchProvider(
```
```text
        base_url=getattr(search_cfg, "base_url", "http://127.0.0.1:8080"),
```
```text
        timeout_seconds=getattr(search_cfg, "timeout_seconds", 6.0),
```
```text
        language=getattr(search_cfg, "language", "en"),
```
```text
        safe_search=getattr(search_cfg, "safe_search", 1),
```
```text
        specialized_fallbacks=getattr(search_cfg, "specialized_fallbacks", True),
```
```text
    )
```
Then update the tool description from “Search DuckDuckGo...” to “Search the web through FRIDAY's local SearXNG service...” and keep the same tool name `online.search`.

### 6.6 `src/friday/app.py` - MODIFY tool registration and later Speech Director wiring
Change the current registration call:
```text
register_online_tools(tool_registry, settings=settings)
```
Do not change the brain-selection logic in `build_orchestrator()`. SearXNG is a tool provider, not a brain.

### 6.7 Exact DDG cleanup in search code
After the SearXNG path works, remove all direct references in `search.py` to:
```text
https://api.duckduckgo.com/
```
```text
https://lite.duckduckgo.com/lite/
```
```text
DuckDuckGoScraper
```
```text
DuckDuckGo
```
Use a repo-wide reference scan before deleting the compatibility alias or root HTML artifacts:
```text
git grep -n -E "DuckDuckGoScraper|api\.duckduckgo\.com|lite\.duckduckgo\.com|ddg(_lite)?\.html|DuckDuckGo" -- .
```
If the only remaining matches are inside `search.py`, `sources.py`, `tools/online.py`, docs, or the two root HTML files, update/delete those matches as described here.

## 7. Phase 3 - Add the Speech Director

### 7.1 ADD `src/friday/interaction/speech_director.py`
Implement this as a pure local Python module. No network calls. No Ollama call. No Gemini call. No Chatterbox model import. It should be cheap enough to run for every sentence.
Use this contract:
```text
@dataclass(frozen=True)
```
```text
class SpeechContext:
```
```text
    user_text: str = ""
```
```text
    task_status: str = ""
```
```text
    awaiting_confirmation: bool = False
```
```text
    tool_name: str = ""
```

```text
@dataclass(frozen=True)
```
```text
class SpeechDecision:
```
```text
    emotion: str
```
```text
    intensity: float
```
```text
    delivery: str
```
```text
    tags: tuple[str, ...] = ()
```

```text
class SpeechDirector:
```
```text
    def decide(self, text: str, context: SpeechContext | None = None) -> SpeechDecision:
```
```text
        ...
```

```text
    def render(self, text: str, context: SpeechContext | None = None) -> str:
```
```text
        ...
```
The public `render()` output is the private TTS text. The model response that FRIDAY prints/logs remains the clean response without bracketed tags.

### 7.2 V1 emotion policy
Start with a very small rule set. The goal is controlled behaviour, not a large taxonomy.
| Situation | Emotion/delivery | Default tag | Notes |
| --- | --- | --- | --- |
| Ordinary factual response | neutral / conversational | none | This is the default. |
| User reports success / FRIDAY confirms success | positive / confident | none initially | Let wording + punctuation carry tone before adding effects. |
| Lightly amusing response where a vocal effect is genuinely appropriate | amused / playful | `[chuckle]` | Use sparingly; never add to ordinary factual answers. |
| Surprise or sudden discovery | surprised | `[gasp]` only after calibration | Gate through the empirical tag test. |
| Empathy after frustration/failure | empathetic / soft | `[sigh]` optionally | Do not use for every apology. |
| Critical/error/blocked action | serious / restrained | none | Avoid laughter or playful tags. |
| Confirmation prompt | calm / clear | none | Do not let Speech Director make confirmations ambiguous. |
| Goodbye / shutdown | calm / warm | none | Use plain language; avoid paralinguistic effects in a security-related flow. |


Important calibration rule: current Chatterbox Turbo documentation confirms native paralinguistic tags, but current upstream issue reports indicate that some emotion-delivery tags may tokenize without having an audible effect in specific implementations. Therefore the first configuration must leave `allow_experimental_emotion_tags: false` and only enable those tags after local A/B audio testing on the exact installed runtime.

### 7.3 Tag allow-lists in `src/friday/interaction/tts.py`
Do not delete existing tag support outright. Refactor the constants into two categories so the Speech Director can distinguish tags that have been explicitly validated on the user's runtime from tags that still require testing.
```text
CHATTERBOX_EVENT_TAGS = {
```
```text
    "clear throat", "sigh", "shush", "cough", "groan",
```
```text
    "sniff", "gasp", "chuckle", "laugh",
```
```text
}
```

```text
CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS = {
```
```text
    "happy", "sarcastic", "whispering", "whisper", "angry",
```
```text
    "surprised", "dramatic", "fear", "crying", "advertisement", "narration",
```
```text
}
```

```text
CHATTERBOX_TAGS = CHATTERBOX_EVENT_TAGS | CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS
```
Keep `clean_tts_text(..., preserve_emotion_tags=True)` as the final sanitation step. Its job is to preserve valid tags and strip Markdown, not to decide which emotion should be used.

### 7.4 Speech Director must be idempotent
Never produce `[chuckle][chuckle] text` because a response was passed through the renderer twice. `render(render(text))` should either equal `render(text)` or safely normalize to one tag.
Also enforce a hard maximum from `voice.speech_director.max_tags_per_sentence`. V1 default is 1.

## 8. Phase 4 - Wire Speech Director into Every Voice Path

### 8.1 `src/friday/app.py` - construct one shared Speech Director
After settings are loaded and the TTS synthesizer is built, instantiate one director from config and pass that same instance into both local VoiceSession and GeminiLiveSession. Do not construct a separate director for every sentence.
```text
from friday.interaction.speech_director import SpeechDirector
```

```text
sd_cfg = getattr(orch.settings.voice, "speech_director", None)
```
```text
speech_director = SpeechDirector(
```
```text
    enabled=getattr(sd_cfg, "enabled", True),
```
```text
    mode=getattr(sd_cfg, "mode", "rules"),
```
```text
    max_tags_per_sentence=getattr(sd_cfg, "max_tags_per_sentence", 1),
```
```text
    allow_vocal_effects=getattr(sd_cfg, "allow_vocal_effects", True),
```
```text
    allow_experimental_emotion_tags=getattr(sd_cfg, "allow_experimental_emotion_tags", False),
```
```text
    log_decisions=getattr(sd_cfg, "log_decisions", False),
```
```text
)
```
If your implementation uses a Pydantic config object directly, prefer passing `sd_cfg` rather than repeating individual fields. The important design requirement is one shared director object per running FRIDAY process.

### 8.2 `src/friday/interaction/session.py` - ADD director dependency
Add `speech_director: Any | None = None` to `VoiceSession.__init__` and store it as `self.speech_director`.
Then integrate at both TTS paths:
| Location | Current action | Required change |
| --- | --- | --- |
| `_process_audio()` legacy path | `self.tts.speak_interruptible(response_text, ...)` | Call the director first and pass the rendered private TTS text to `speak_interruptible`. |
| `_speak_event_driven()` | `StreamingTts` receives the clean response text | Render the response before constructing/feeding the `LlmStreamToTts` bridge. |
| Speculative acknowledgement | `self.tts.speak_interruptible("On it, working on that now.", ...)` | Leave unchanged in V1 or route through director with a neutral/positive context; do not inject emotional effects into acknowledgement unless necessary. |


Store the current user transcript on the session object so the director can use conversational context. The director should never change the semantic content of the response.

### 8.3 `src/friday/interaction/gemini_live.py` - ADD director dependency
Add `speech_director` to `GeminiLiveSession.__init__`, store it, and apply `render()` to each complete sentence immediately before the sentence is put onto `tts_queue`.
Update the input-transcription branch so the latest user text is saved, for example as `self._last_user_text`. Use that value as `SpeechContext.user_text` when rendering the next assistant sentence.
The Gemini Live model must continue producing clean text. Do not instruct Gemini to emit Chatterbox tags in its response. This preserves a single speech-policy layer across Qwen and Gemini.

### 8.4 `src/friday/interaction/pipeline.py` - do not move speech policy into StreamingTts
The current pipeline's `StreamingTts` object should remain a transport/scheduling layer. Do not put emotion selection inside `StreamingTts`. This avoids coupling speech policy to audio queue mechanics and keeps the same director usable by Gemini Live.

## 9. Phase 5 - Empirical Chatterbox Tag Calibration
This phase is mandatory before enabling experimental emotion-delivery tags. Do not assume that because a tag tokenizes, it changes the audio on the installed runtime.

### 9.1 ADD a test script
Create `scripts/test_chatterbox_tags.py` that loads the existing Chatterbox Turbo synthesizer and produces one WAV per tag using the same voice reference and configuration FRIDAY uses in production.
The test set should include these control/variant pairs:
```text
Baseline:
```
```text
  "I understand. We can work through this together."
```

```text
Event tags:
```
```text
  [sigh]
```
```text
  [gasp]
```
```text
  [chuckle]
```
```text
  [laugh]
```

```text
Experimental emotion tags:
```
```text
  [happy]
```
```text
  [sarcastic]
```
```text
  [whispering]
```
```text
  [angry]
```
```text
  [surprised]
```
```text
  [dramatic]
```
```text
  [fear]
```
```text
  [crying]
```
Store results outside git, for example `data/eval/chatterbox_tag_test/`. Do not commit generated WAVs unless you deliberately want them in the repository.

### 9.2 Pass/fail criteria
| Check | Pass condition | Failure action |
| --- | --- | --- |
| Tag is consumed | Bracket tag is not spoken literally. | Fix tag sanitation before any further testing. |
| Tag changes sound | A human listener can reliably distinguish the tagged variant from baseline. | Keep tag disabled in V1. |
| No destructive artifact | No repeated noise, clipping, strange vowels, or major speaker-identity loss. | Disable the tag. |
| Context fit | The effect matches the intended emotion and is not comical in ordinary responses. | Do not map the tag to that emotion. |
| Repeatability | Effect remains reasonably stable across several utterances. | Keep experimental. |


Record the results in `docs/voice-baseline.md` or a dedicated `docs/speech-director-calibration.md`. Do not make the calibration result depend on subjective claims about the language model; the test is specifically about audio output.

## 10. Phase 6 - Unit and Integration Tests

### 10.1 ADD `tests/online/test_search.py`
Required cases:
- Empty query returns an empty list without network calls.
- Successful SearXNG JSON response is mapped into `SearchResult(title, url, snippet)`.
- Missing `content` field falls back to an empty snippet without crashing.
- Duplicate URLs are removed.
- `max_results` is respected.
- Timeout and connection errors do not raise out of the tool boundary.
- HTTP 403/500 from SearXNG triggers the configured fallback or returns a clean error result.
- Wikipedia and Google News fallbacks still work through mocked responses.
- No direct DDG endpoint is called by the provider.

### 10.2 ADD `tests/interaction/test_speech_director.py`
Required cases:
- Default text gets a neutral decision and no tags.
- Failure/error context never receives a laugh/chuckle tag.
- Empathy rule can emit `[sigh]` only when configured and allowed.
- Playful rule can emit `[chuckle]` only when configured and appropriate.
- Experimental emotion tags are blocked when `allow_experimental_emotion_tags=False`.
- Maximum tags per sentence is enforced.
- Repeated rendering does not duplicate tags.
- Director never changes the semantic words in the response.

### 10.3 ADD `tests/interaction/test_tts_tags.py`
Test `clean_tts_text()` directly. Verify Markdown is removed while supported bracketed tags survive, including tags with spaces such as `[clear throat]` and `[throat-clearing]`. Also verify `preserve_emotion_tags=False` strips them.

### 10.4 Extend existing voice integration coverage
The repository already has `tests/interaction/test_event_driven_voice_integration.py` and `tests/interaction/test_voice_e2e_matrix.py`. Add at least one assertion that the TTS transport receives a director-rendered string while the user-facing response remains unmodified.
Do not make live network calls from unit tests. SearXNG API tests should be mocked; the SearXNG container is verified separately by the manual smoke checklist.

## 11. Phase 7 - Documentation and Stale Text Cleanup
| File | Action | Exact documentation change |
| --- | --- | --- |
| `README.md` | MODIFY | Replace DDG search description with local SearXNG + Wikipedia + Google News. Replace the statement that TTS has no bracket tags in the output path with: LLM output remains clean; Speech Director injects private Chatterbox tags before synthesis. |
| `src/friday/interaction/pipeline.py` | MODIFY | Replace stale Piper references in module/docstrings with Chatterbox Turbo. |
| `src/friday/interaction/streaming_tts.py` | MODIFY | Replace stale Piper references with Chatterbox Turbo. |
| `src/friday/interaction/tts.py` | MODIFY | Document verified event tags versus experimental emotion tags; state that the Speech Director, not the LLM, decides tags. |
| `CHANGELOG.md` | ADD | Record SearXNG search backend and Speech Director changes. |
| `docs/runbooks/` | ADD | Commit a Markdown copy of this run book so the repository contains the operational procedure. |


Do not edit historical implementation summaries solely to make them look current unless they are explicitly maintained as living documentation. The goal is to avoid rewriting history.

## 12. Exact Files to Add / Modify / Remove
| Action | Path | Required change |
| --- | --- | --- |
| ADD | `ops/searxng/docker-compose.yml` | Official SearXNG Compose template. |
| ADD | `ops/searxng/.env.example` | Official SearXNG env template. |
| ADD | `ops/searxng/core-config/settings.yml` | Local JSON-enabled SearXNG settings. |
| ADD | `src/friday/interaction/speech_director.py` | Rule-based Speech Director. |
| ADD | `tests/online/test_search.py` | Mocked SearXNG/fallback tests. |
| ADD | `tests/interaction/test_speech_director.py` | Speech policy tests. |
| ADD | `tests/interaction/test_tts_tags.py` | Tag sanitation/preservation tests. |
| ADD | `scripts/test_chatterbox_tags.py` | Manual audio calibration utility. |
| MODIFY | `src/friday/config.py` | Add SearchConfig and SpeechDirectorConfig. |
| MODIFY | `config/default.yaml` | Add search and speech_director config. |
| MODIFY | `src/friday/online/search.py` | SearXNG primary; keep Wikipedia/Google News; remove direct DDG. |
| MODIFY | `src/friday/online/sources.py` | Register SearXNG as search source. |
| MODIFY | `src/friday/tools/online.py` | Inject settings into search provider; update description. |
| MODIFY | `src/friday/app.py` | Pass settings to online tools; construct/inject shared Speech Director. |
| MODIFY | `src/friday/interaction/session.py` | Inject director and render TTS text in both legacy and event-driven paths. |
| MODIFY | `src/friday/interaction/gemini_live.py` | Inject director and render sentence text before Chatterbox queueing. |
| MODIFY | `src/friday/interaction/tts.py` | Split/label tag allow-lists; keep final tag preservation. |
| MODIFY | `src/friday/interaction/pipeline.py` | Fix stale Piper documentation only. |
| MODIFY | `src/friday/interaction/streaming_tts.py` | Fix stale Piper documentation only. |
| MODIFY | `README.md` | Update search/TTS architecture and local service setup. |
| MODIFY | `CHANGELOG.md` | Add change entry. |
| REMOVE | `ddg.html` | Delete after `git grep` confirms it is unused. |
| REMOVE | `ddg_lite.html` | Delete after `git grep` confirms it is unused. |
| REMOVE | Direct DDG code in `search.py` | Delete API and Lite fallback blocks. |
| REMOVE | `DuckDuckGoScraper` alias | Delete after reference scan confirms no external dependency. |
| DO NOT REMOVE | `requirements.txt` | Keep `requests` and `beautifulsoup4`. |
| DO NOT REMOVE | `chatterbox-tts` | Existing TTS dependency stays. |
| DO NOT REMOVE | `models/chatterbox-turbo` | Existing local checkpoint/model stays. |
| DO NOT REMOVE | `models/voice_reference.wav` | Existing speaker reference stays. |



## 13. Phase 8 - Cutover Sequence
Use separate commits. This makes rollback easy and allows you to diagnose search and voice problems independently.
| Commit | Suggested message | Contents |
| --- | --- | --- |
| 1 | `chore: add local searxng deployment` | `ops/searxng/*`, `.gitignore` update if needed. |
| 2 | `feat(search): make searxng the primary provider` | Config + search provider + online tool + source registry + search tests. |
| 3 | `feat(voice): add rule-based speech director` | Speech Director + config + unit tests. |
| 4 | `feat(voice): route all tts through speech director` | app/session/Gemini Live/tts tag integration. |
| 5 | `test(voice): add chatterbox tag calibration harness` | Calibration script + TTS sanitation tests. |
| 6 | `docs: update search and speech architecture` | README, stale Piper text, changelog, committed runbook copy. |
| 7 | `chore: remove direct duckduckgo integration` | Remove DDG blocks and orphaned HTML once validated. |



## 14. Verification Matrix
| Area | Command / action | Expected result |
| --- | --- | --- |
| Python config | `python -c "from friday.config import Settings; print(Settings.load(...).search)"` | Search config validates and loads. |
| SearXNG service | `docker compose ps` in `ops/searxng` | `searxng-core` and `searxng-valkey` are running. |
| SearXNG JSON | PowerShell `Invoke-RestMethod` against `/search?...&format=json` | JSON response contains a non-empty `results` list for a common query. |
| FRIDAY search | `python -m friday --text`, then an online search request | Tool uses local SearXNG and returns titles/snippets. |
| No DDG dependency | `git grep -n` scan | No direct DDG API/Lite references remain in runtime search code. |
| Local voice | `python -m friday` | Event-driven path starts; TTS still uses Chatterbox. |
| Gemini voice | `python -m friday --gemini` | Gemini Live still streams response text, then Speech Director, then Chatterbox. |
| Tag safety | Run `scripts/test_chatterbox_tags.py` | Only validated tags are enabled for production. |
| Regression | `pytest tests/ -q` | All existing and new tests pass. |
| Lint/type check | `ruff check src tests` and `mypy src` | No new lint/type errors attributable to this change. |



## 15. Manual Voice Acceptance Tests
1. Ask a neutral factual question. FRIDAY should answer normally with no strange vocal effects.
2. Tell FRIDAY you solved a bug. The response should sound naturally positive; it should not laugh unless the Speech Director rule explicitly decides that the context supports it.
3. Create a failing tool action. The response must remain serious and must never receive a playful tag.
4. Trigger a confirmation prompt. The response must remain clear and must not insert effects that obscure the confirmation language.
5. Interrupt FRIDAY while speaking. Barge-in must still stop Chatterbox audio and return to listening exactly as before.
6. Use the local Qwen brain and then the Gemini brain for equivalent questions. The speech policy should behave consistently across both brains.
7. Ask for a fresh news topic. Search should hit the local SearXNG endpoint; the answer should still be able to fall back to Google News for current news-specific results.
8. Disconnect/stop SearXNG. `online.search` must fail gracefully or use its configured specialized fallbacks instead of crashing the assistant.

## 16. Security / Reliability Rules
- Bind the SearXNG host port to `127.0.0.1` in the local setup. Do not expose the service publicly just to make FRIDAY work.
- Do not commit `ops/searxng/.env`; it contains the instance secret.
- Do not let user text choose the SearXNG base URL. The URL comes from trusted configuration only.
- Do not let LLM output choose Chatterbox tags directly. The Speech Director owns tag selection.
- Do not use a network LLM to decide speech emotion in the first version; that would add latency and a new failure path to every utterance.
- Do not allow experimental emotion tags by default. Empirically validate them on the exact runtime first.
- Do not alter security tiers or confirmation semantics as part of these changes.
- Keep semantic response text and private TTS-rendered text separate for logging, debugging, and auditability.

## 17. Rollback Procedure
Search rollback:
```text
git log --oneline --decorate -10
```
```text
# identify the commit immediately before the search cutover
```
```text
git revert <search-cutover-commit>
```
Operational rollback for SearXNG only:
```text
cd ops\searxng
```
```text
docker compose down
```
The existing code path can then be restored from git. The local SearXNG directory can remain on disk for later reactivation, or be deleted after all FRIDAY references are reverted.
Voice rollback: disable the Speech Director without removing code by setting:
```text
voice:
```
```text
  speech_director:
```
```text
    enabled: false
```
The session should then pass clean response text directly to the existing Chatterbox TTS path. This is the required emergency switch for any regression involving audio playback or barge-in.

## 18. What NOT to Change in This Run
| File / subsystem | Do not change |
| --- | --- |
| `models/*` | Do not replace or redownload Chatterbox Turbo or the voice reference. |
| Qwen/Gemini model routing | Do not change the model names, provider logic, or brain selector just because Speech Director is being added. |
| Security policy | Do not alter risk tiers, confirmation policy, voice authentication, or passphrase rules. |
| Audio capture / VAD | Do not modify microphone/VAD thresholds unless a regression is independently proven. |
| `StreamingTts` semantics | Do not mix speech policy into queue generation/cancellation mechanics. |
| Google integrations | No changes to Gmail/Calendar are required. |
| Docker Desktop settings | Do not change unrelated WSL2/Hyper-V settings if Docker already works. |



## 19. Future Phase - Gemini as Speech-Director Evaluator
This is intentionally not part of the first production cutover. After the deterministic Speech Director has stable behaviour, collect a small evaluation dataset instead of fine-tuning a large conversational brain.
```text
Example JSONL record:
```
```text
{"user":"I finally fixed the bug.","assistant":"That is excellent. Nice work.","context":{"task_status":"COMPLETED"},"decision":{"emotion":"positive","tags":[]},"human_rating":4}
```
```text
{"user":"Nothing works and I am stuck.","assistant":"Let's slow down and work through it.","context":{"task_status":"FAILED"},"decision":{"emotion":"empathetic","tags":["sigh"]},"human_rating":5}
```
Target the Speech Director, not Qwen/Gemini. Gemini can be used later to propose or critique labels, while human acceptance remains the final gate for the dataset. A learned local director can replace the rule-based selector only after enough examples exist and its latency/safety characteristics are known.

## 20. Final Definition of Done
| Gate | Must be true |
| --- | --- |
| Search service | SearXNG is reachable on `127.0.0.1:8080` and JSON output is enabled. |
| Search integration | `online.search` uses SearXNG as primary and preserves Wikipedia/Google News specialized fallbacks. |
| DDG removal | FRIDAY runtime has no direct DDG API or DDG Lite calls. |
| Configuration | Search and Speech Director settings are Pydantic-validated and YAML-configurable. |
| Speech Director | One shared, deterministic director exists and is used by local legacy TTS, event-driven TTS, and Gemini Live. |
| LLM isolation | Qwen/Gemini produce clean semantic text; they do not own Chatterbox tags. |
| TTS safety | Experimental emotion tags stay disabled until local audio calibration passes. |
| Regression | Full test suite passes, including search, TTS tag sanitation, and voice integration coverage. |
| Documentation | README and stale Piper references are corrected; changelog is updated. |
| Rollback | Speech Director can be disabled via config without reverting the entire project. |



## 21. Official References Used by This Run Book
SearXNG container installation documentation: https://docs.searxng.org/admin/installation-docker.html
SearXNG Search API documentation: https://docs.searxng.org/dev/search_api.html
SearXNG settings documentation: https://docs.searxng.org/admin/settings/settings.html
SearXNG official Compose template: https://github.com/searxng/searxng/blob/master/container/docker-compose.yml
SearXNG official `.env.example`: https://raw.githubusercontent.com/searxng/searxng/master/container/.env.example
Docker Desktop Windows installation documentation: https://docs.docker.com/desktop/setup/install/windows-install/
Chatterbox official repository / Turbo documentation: https://github.com/resemble-ai/chatterbox
Chatterbox upstream discussion/issue showing that tag behaviour can vary by implementation: https://github.com/resemble-ai/chatterbox/issues/557

## Appendix A - Exact Folder Layout After Completion
```text
.
```
```text
├── config/
```
```text
│   ├── default.yaml                 # MODIFIED
```
```text
│   └── gemini.yaml                  # unchanged in v1
```
```text
├── ops/
```
```text
│   └── searxng/
```
```text
│       ├── docker-compose.yml       # ADDED (official template)
```
```text
│       ├── .env.example             # ADDED (official template)
```
```text
│       ├── .env                     # LOCAL ONLY, NOT COMMITTED
```
```text
│       └── core-config/
```
```text
│           └── settings.yml         # ADDED
```
```text
├── scripts/
```
```text
│   └── test_chatterbox_tags.py      # ADDED
```
```text
├── src/friday/
```
```text
│   ├── config.py                    # MODIFIED
```
```text
│   ├── app.py                       # MODIFIED
```
```text
│   ├── online/
```
```text
│   │   ├── search.py                # MODIFIED
```
```text
│   │   └── sources.py               # MODIFIED
```
```text
│   ├── interaction/
```
```text
│   │   ├── gemini_live.py           # MODIFIED
```
```text
│   │   ├── pipeline.py              # MODIFIED (docs only)
```
```text
│   │   ├── session.py               # MODIFIED
```
```text
│   │   ├── speech_director.py       # ADDED
```
```text
│   │   ├── streaming_tts.py         # MODIFIED (docs only)
```
```text
│   │   └── tts.py                   # MODIFIED
```
```text
│   └── tools/
```
```text
│       └── online.py                # MODIFIED
```
```text
├── tests/
```
```text
│   ├── online/
```
```text
│   │   └── test_search.py           # ADDED
```
```text
│   └── interaction/
```
```text
│       ├── test_speech_director.py  # ADDED
```
```text
│       └── test_tts_tags.py          # ADDED
```
```text
├── README.md                        # MODIFIED
```
```text
├── CHANGELOG.md                     # MODIFIED
```
```text
├── ddg.html                        # REMOVED
```
```text
└── ddg_lite.html                   # REMOVED
```

## Appendix B - One-Pass Operator Checklist
- ☐ Baseline tests pass before changes.
- ☐ SearXNG Compose and `.env.example` downloaded from official upstream sources.
- ☐ Local `.env` contains a generated secret and is ignored by git.
- ☐ SearXNG JSON format enabled in `core-config/settings.yml`.
- ☐ SearXNG responds on `127.0.0.1:8080`.
- ☐ Search provider uses configuration instead of a hard-coded global instance.
- ☐ Wikipedia and Google News remain available as specialized fallbacks.
- ☐ Direct DDG API/Lite blocks are removed from runtime code.
- ☐ Speech Director is deterministic, local, and disabled for experimental tags by default.
- ☐ All three voice transports route through the same Speech Director policy.
- ☐ Chatterbox tag calibration has been performed before enabling experimental tags.
- ☐ User-visible response text remains clean and tag-free.
- ☐ Barge-in/interruption remains functional.
- ☐ Full tests, Ruff, and mypy pass.
- ☐ README / changelog / stale Piper references are updated.
- ☐ Rollback switch `voice.speech_director.enabled=false` has been verified.