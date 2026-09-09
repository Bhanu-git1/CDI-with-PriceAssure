"""
Data source router.

Decides which registered data source a natural-language question belongs to,
using a four-stage cascade that runs cheapest-first and is deterministic
wherever it can be:

  Stage 0  explicit override   — UI selection, in-prompt directive, sticky
                                 follow-up. Wins outright.
  Stage 1  deterministic score — keyword/entity scoring from datasources.yaml.
                                 Routes only when the winner is convincing AND
                                 clearly ahead of the runner-up.
  Stage 2  LLM tie-break       — one small classification call with a compact
                                 source catalogue. No schema is sent.
  Stage 3  abstain             — below the confidence floor, ask the user which
                                 source they meant instead of guessing.

Stage 3 is the important one: answering from the wrong database is worse than
asking a one-line clarifying question.
"""

import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("source-router")

# Score weights. An explicit table/object name is near-proof; a strong keyword
# is decisive for exactly one source (enforced at registry load); weak keywords
# only contribute.
W_ENTITY = 10
W_STRONG = 6
W_WEAK = 2
W_EXCLUDE = -8

# Words that mark a turn as a refinement of the previous one rather than a new
# question, used by the sticky-follow-up rule.
FOLLOWUP_MARKERS = (
    "those", "them", "that", "it", "same", "again", "instead",
    "also", "and", "now", "then", "what about", "how about",
    "top", "first", "last", "more", "fewer", "only", "just",
    "group", "sort", "order", "filter", "expand", "drill",
)

GREETINGS = {
    "hi", "hello", "hey", "help", "thanks", "thank you", "ok", "okay",
    "good morning", "good afternoon", "good evening", "yo", "hola",
}


@dataclass
class RouteDecision:
    """Outcome of routing one question."""

    source_id: Optional[str]
    stage: str
    confidence: float = 1.0
    reason: str = ""
    needs_clarification: bool = False
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    scores: Dict[str, int] = field(default_factory=dict)

    def to_public(self) -> Dict[str, Any]:
        """Routing metadata attached to the chat response, for the UI badge."""
        return {
            "source_id": self.source_id,
            "stage": self.stage,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "needs_clarification": self.needs_clarification,
            "candidates": self.candidates,
            "scores": self.scores,
        }


def _keyword_pattern(keyword: str) -> str:
    """
    Word-boundary pattern for a keyword, tolerating a simple plural.

    Boundary matching replaces the previous naive substring test, which matched
    "rep" inside "report" and "prepare". The optional plural suffix is what
    keeps phrases like "work detail" matching "work details", preserving the
    old substring behaviour where it was actually wanted.
    """
    parts = keyword.lower().split()
    if not parts:
        return r"(?!x)x"  # never matches
    escaped = [re.escape(p) for p in parts[:-1]]
    last = re.escape(parts[-1]) + r"(?:e?s)?"
    body = r"\s+".join(escaped + [last])
    return r"(?<![\w])" + body + r"(?![\w])"


# A source alias only counts as a directive when the user actually addresses
# the source — "in gpo", "from salesforce", "@gpo", "gpo:". A bare mention does
# not: "Show Salesforce sync status" is a question about DB 1's sync audit
# tables, not a request to query the Salesforce org.
_DIRECTIVE_PREFIX = r"(?:(?:in|from|on|using|against|within|query|querying|ask|check)\s+(?:the\s+)?|@)"


def _alias_pattern(alias: str) -> str:
    body = r"\s+".join(re.escape(p) for p in alias.lower().split())
    return (
        r"(?<![\w])(?:"
        + _DIRECTIVE_PREFIX + body + r"(?![\w])"      # "in gpo", "@gpo"
        + r"|" + body + r"\s*:"                        # "gpo: how many batches"
        + r")"
    )


class _CompiledRules:
    """Pre-compiled matchers for one source's routing vocabulary."""

    def __init__(self, ctx):
        self.ctx = ctx
        r = ctx.routing
        self.entities = [(e, re.compile(_keyword_pattern(e), re.I)) for e in r.entities]
        self.strong = [(k, re.compile(_keyword_pattern(k), re.I)) for k in r.strong_keywords]
        self.weak = [(k, re.compile(_keyword_pattern(k), re.I)) for k in r.weak_keywords]
        self.exclude = [(k, re.compile(_keyword_pattern(k), re.I)) for k in r.exclude_keywords]
        self.aliases = [(a, re.compile(_alias_pattern(a), re.I)) for a in ctx.aliases]

    def score(self, text: str):
        """Returns (score, matched_terms, has_decisive)."""
        total = 0
        hits = []
        decisive = False
        for label, weight, pairs in (
            ("entity", W_ENTITY, self.entities),
            ("strong", W_STRONG, self.strong),
            ("weak", W_WEAK, self.weak),
            ("exclude", W_EXCLUDE, self.exclude),
        ):
            for term, rx in pairs:
                if rx.search(text):
                    total += weight
                    hits.append(f"{term}({label})")
                    if label in ("entity", "strong"):
                        decisive = True
        return total, hits, decisive

    def alias_hit(self, text: str) -> Optional[str]:
        for term, rx in self.aliases:
            if rx.search(text):
                return term
        return None


class SourceRouter:
    def __init__(self, registry, classifier: Optional[Callable[[str, str], Awaitable[str]]] = None):
        """
        registry   — DataSourceRegistry
        classifier — async callable(prompt, purpose) -> raw LLM text, used only
                     for the Stage-2 tie-break. Injected so the router carries
                     no dependency on a particular LLM provider, and so tests
                     can run the deterministic stages with no LLM at all.
        """
        self.registry = registry
        self.config = registry.router_config
        self.classifier = classifier
        self._rules = {ctx.id: _CompiledRules(ctx) for ctx in registry.all()}
        self._cache: "OrderedDict[str, RouteDecision]" = OrderedDict()

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(message: str) -> str:
        return " ".join((message or "").lower().split())

    def _cache_get(self, message: str) -> Optional[RouteDecision]:
        key = self._cache_key(message)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, message: str, decision: RouteDecision):
        key = self._cache_key(message)
        self._cache[key] = decision
        self._cache.move_to_end(key)
        while len(self._cache) > self.config.decision_cache_size:
            self._cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Stage 0 — explicit override
    # ------------------------------------------------------------------

    def _explicit(self, message: str, requested: Optional[str]) -> Optional[RouteDecision]:
        # 0a. The UI told us. Nothing overrides a deliberate user choice.
        if requested and requested not in ("auto", "", None):
            ctx = self.registry.get(requested)
            if ctx is not None:
                return RouteDecision(
                    source_id=ctx.id, stage="explicit", confidence=1.0,
                    reason=f"You selected {ctx.short_label}.",
                )
            logger.warning(f"Requested unknown source '{requested}'; falling back to routing.")

        # 0b. The prompt names a source ("in gpo", "from salesforce", "db 2").
        text = message or ""
        alias_matches = []
        for sid, rules in self._rules.items():
            hit = rules.alias_hit(text)
            if hit:
                alias_matches.append((sid, hit))
        if len(alias_matches) == 1:
            sid, term = alias_matches[0]
            return RouteDecision(
                source_id=sid, stage="alias", confidence=0.98,
                reason=f"Your question names '{term}'.",
            )
        return None

    def _sticky(self, message: str, previous_source_id: Optional[str]) -> Optional[RouteDecision]:
        """
        Keep the previous source for a short refinement turn.

        Without this, "show me the top 5" after a GPO answer falls back to the
        default source and silently answers from the wrong database.
        """
        if not self.config.sticky_followup or not previous_source_id:
            return None
        if self.registry.get(previous_source_id) is None:
            return None

        text = (message or "").strip().lower()
        tokens = re.findall(r"[\w']+", text)
        if not tokens or len(tokens) > self.config.sticky_max_tokens:
            return None

        # A follow-up must not itself name a competing source.
        for sid, rules in self._rules.items():
            if sid == previous_source_id:
                continue
            _, _, decisive = rules.score(text)
            if decisive:
                return None

        looks_like_followup = any(m in text for m in FOLLOWUP_MARKERS)
        if not looks_like_followup:
            return None

        ctx = self.registry.require(previous_source_id)
        return RouteDecision(
            source_id=previous_source_id, stage="sticky", confidence=0.85,
            reason=f"Follow-up to your previous {ctx.short_label} question.",
        )

    # ------------------------------------------------------------------
    # Stage 1 — deterministic scoring
    # ------------------------------------------------------------------

    def score_all(self, message: str) -> Dict[str, Dict[str, Any]]:
        text = message or ""
        out = {}
        for sid, rules in self._rules.items():
            score, hits, decisive = rules.score(text)
            out[sid] = {
                "score": score,
                "hits": hits,
                "decisive": decisive,
                "priority": rules.ctx.priority,
            }
        return out

    def _deterministic(self, message: str) -> (Optional[RouteDecision], Dict[str, Dict[str, Any]]):
        """
        Decide from keyword evidence alone, or return None to escalate.

        Only entity and strong-keyword hits are DECISIVE. Weak keywords are
        shared vocabulary ("member", "status", "customer"), so they contribute
        to ranking but may never, on their own, pick a source over another
        source's decisive evidence.
        """
        scored = self.score_all(message)
        # Rank by score, then by manifest priority as an epsilon tie-break —
        # priority is never large enough to overturn a keyword difference.
        ranked = sorted(
            scored.items(),
            key=lambda kv: (kv[1]["score"], kv[1]["priority"]),
            reverse=True,
        )
        scores_only = {sid: v["score"] for sid, v in scored.items()}
        if not ranked:
            return None, scored

        decisive_ids = [sid for sid, v in scored.items() if v["decisive"]]

        # Exactly one source produced decisive evidence — unambiguous, whatever
        # weak noise the others picked up.
        if len(decisive_ids) == 1:
            sid = decisive_ids[0]
            return RouteDecision(
                source_id=sid, stage="score", confidence=0.9,
                reason=f"Matched {', '.join(scored[sid]['hits'][:4])}.",
                scores=scores_only,
            ), scored

        # Several sources have decisive evidence: require a clear winner,
        # otherwise escalate. This margin is the defence against answering an
        # ambiguous question from the wrong source.
        if len(decisive_ids) > 1:
            top_id, top = ranked[0]
            second = ranked[1][1]["score"] if len(ranked) > 1 else 0
            if top["score"] >= self.config.min_score and (top["score"] - second) >= self.config.min_margin:
                return RouteDecision(
                    source_id=top_id, stage="score", confidence=0.88,
                    reason=f"Matched {', '.join(top['hits'][:4])}.",
                    scores=scores_only,
                ), scored
            return None, scored

        # No decisive evidence anywhere — weak vocabulary only. Route to the
        # clear weak winner if there is one, else let the caller fall back to
        # the default source. Never ask for clarification here: the previous
        # behaviour for unrecognised questions was to use the default source,
        # and weak-only signal is too thin to justify interrupting the user.
        top_id, top = ranked[0]
        second = ranked[1][1]["score"] if len(ranked) > 1 else 0
        if top["score"] > 0 and (top["score"] - second) >= self.config.min_margin:
            return RouteDecision(
                source_id=top_id, stage="score_weak", confidence=0.6,
                reason=f"Matched {', '.join(top['hits'][:4])}.",
                scores=scores_only,
            ), scored

        ctx = self.registry.default()
        return RouteDecision(
            source_id=ctx.id, stage="default", confidence=0.4,
            reason=f"No source-specific terms recognised; used {ctx.short_label}.",
            scores=scores_only,
        ), scored

    # ------------------------------------------------------------------
    # Stage 2 — LLM tie-break
    # ------------------------------------------------------------------

    def _catalogue_prompt(self, message: str) -> str:
        lines = [
            "You classify a user's data question to exactly one data source.",
            "Choose from the sources below and reply with JSON only.",
            "",
            "SOURCES:",
        ]
        for ctx in self.registry.all():
            domain = " ".join((ctx.routing.domain or "").split())
            entities = ", ".join(ctx.routing.entities[:12])
            lines.append(f"- id: {ctx.id}")
            lines.append(f"  name: {ctx.label}")
            lines.append(f"  covers: {domain}")
            if entities:
                lines.append(f"  example tables/objects: {entities}")
        lines += [
            "",
            f"QUESTION: {message}",
            "",
            "Reply with ONLY this JSON object:",
            '{"source_id": "<one id from the list>", "confidence": <0.0-1.0>, '
            '"alternatives": ["<other plausible ids>"], "reason": "<one short sentence>"}',
            "",
            "Set confidence below 0.6 when the question could genuinely be answered "
            "from more than one source, and list those in alternatives.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _parse_classifier(text: str) -> Dict[str, Any]:
        if not text:
            return {}
        raw = text.strip()
        if "```" in raw:
            block = raw.split("```", 2)
            raw = block[1] if len(block) > 1 else raw
            if raw.lstrip().lower().startswith("json"):
                raw = raw.lstrip()[4:]
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]
        try:
            return json.loads(raw, strict=False)
        except Exception:
            return {}

    async def _llm_tiebreak(self, message: str, scored: dict) -> Optional[RouteDecision]:
        if self.classifier is None:
            return None
        try:
            raw = await self.classifier(self._catalogue_prompt(message), "source-classification")
        except Exception as e:
            logger.warning(f"Source classifier call failed: {e}")
            return None

        parsed = self._parse_classifier(raw)
        sid = parsed.get("source_id")
        if sid not in self.registry.ids():
            logger.warning(f"Classifier returned unusable source_id {sid!r}")
            return None

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        alternatives = [a for a in (parsed.get("alternatives") or []) if a in self.registry.ids() and a != sid]
        reason = str(parsed.get("reason") or "").strip()

        return RouteDecision(
            source_id=sid, stage="llm", confidence=confidence,
            reason=reason or "Classified by the model.",
            candidates=[{"id": a} for a in alternatives],
            scores={k: v["score"] for k, v in scored.items()},
        )

    # ------------------------------------------------------------------
    # Stage 3 — abstain
    # ------------------------------------------------------------------

    def _clarify(self, scored: dict, candidate_ids: Optional[List[str]] = None,
                 note: str = "") -> RouteDecision:
        if candidate_ids:
            ids = [i for i in candidate_ids if self.registry.get(i)]
        else:
            positives = [(sid, v["score"]) for sid, v in scored.items() if v["score"] > 0]
            positives.sort(key=lambda kv: -kv[1])
            ids = [sid for sid, _ in positives[:3]] or self.registry.ids()[:3]

        candidates = []
        for sid in ids:
            ctx = self.registry.require(sid)
            candidates.append({
                "id": ctx.id,
                "label": ctx.short_label,
                "badge": ctx.badge,
                "why": " ".join((ctx.routing.domain or "").split())[:160],
            })

        return RouteDecision(
            source_id=None, stage="clarify", confidence=0.0,
            reason=note or "The question could apply to more than one data source.",
            needs_clarification=True,
            candidates=candidates,
            scores={k: v["score"] for k, v in scored.items()},
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def is_greeting(self, message: str) -> bool:
        text = " ".join((message or "").lower().split()).strip(" .!?,")
        return text in GREETINGS

    async def route(
        self,
        message: str,
        requested_source: Optional[str] = None,
        previous_source_id: Optional[str] = None,
    ) -> RouteDecision:
        # Stage 0 — explicit override.
        decision = self._explicit(message, requested_source)
        if decision:
            return decision

        # A bare greeting is not a data question; answer it from the default
        # source rather than asking which database the user means.
        if self.is_greeting(message):
            return RouteDecision(
                source_id=previous_source_id or self.registry.default_source_id,
                stage="greeting", confidence=1.0,
                reason="Greeting — no data source needed.",
            )

        decision = self._sticky(message, previous_source_id)
        if decision:
            return decision

        cached = self._cache_get(message)
        if cached is not None and not cached.needs_clarification:
            return cached

        # Stage 1 — deterministic scoring.
        decision, scored = self._deterministic(message)
        if decision:
            self._cache_put(message, decision)
            return decision

        # Stage 2 — LLM tie-break.
        decision = await self._llm_tiebreak(message, scored)
        if decision and decision.confidence >= self.config.min_llm_confidence and not decision.candidates:
            self._cache_put(message, decision)
            return decision

        # Stage 3 — abstain rather than guess.
        #
        # Reached only when several sources produced decisive evidence and
        # neither the margin nor the classifier could separate them.
        if decision:
            ids = [decision.source_id] + [c["id"] for c in decision.candidates]
            return self._clarify(
                scored, ids,
                note=decision.reason or "More than one data source could answer this.",
            )

        return self._clarify(scored)
