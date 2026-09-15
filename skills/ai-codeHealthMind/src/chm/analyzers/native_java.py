"""Built-in deterministic Java analyzer.

Pure standard library.  No process, no network, no LLM, no parser dependency:
a *deliberately crude* but fully deterministic line/brace parser is used to
locate declarations and bodies.  Everything it emits is a ``RawFinding`` with
``EvidenceKind.DETERMINISTIC`` and goes through the same dedup / evidence
pipeline as PMD, SpotBugs or Semgrep output.

Design rules (spec §4/§10, false-positive red lines MEDIUM+ <= 8%, HIGH+ <= 3%):

* **Silence beats noise.**  Every rule has an explicit counter-example
  suppression block; when any suppression signal is present the rule emits
  nothing.  Recall is sacrificed on purpose.
* **Determinism.**  No ``set`` iteration decides output order, no timestamps,
  no randomness.  Two runs on the same change set are byte-identical.
* **Changed lines only.**  Unless ``ctx.options["whole_file"]`` is set, a
  finding is only emitted when at least one line of its range is in the diff.
  Cross-file rules still *read* the whole repository but only *report* on
  changed lines.
* **Evidence.**  Every finding carries ``extra["matched_snippet"]``,
  ``extra["line"]`` and ``extra["reason"]`` so a human can re-check it.

------------------------------------------------------------------------------
rule_id                                     sev      category          counter-examples suppressed
------------------------------------------------------------------------------
CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD          MEDIUM   DEAD_CODE         @Scheduled(DEAD-003) @EventListener
                                                                      @PostConstruct @Bean @KafkaListener(DEAD-006)
                                                                      @RabbitListener @JmsListener @XxlJob @Async
                                                                      @Cacheable; name in string literal
                                                                      (reflection DEAD-005); name in xml/yml/props
                                                                      (MyBatis DEAD-004); interface bodies
CHM-JAVA-NAT-UNUSED-FIELD                   LOW      DEAD_CODE         @Autowired/@Resource/@Value/@Inject/@Getter
                                                                      @Setter/@Data/@JsonProperty; name in xml or
                                                                      as a string literal (serialisation)
CHM-JAVA-NAT-UNREACHABLE-BRANCH             LOW      DEAD_CODE         -
CHM-JAVA-NAT-COMMENTED-CODE                 LOW      DEAD_CODE         comment runs shorter than 5 lines
CHM-JAVA-NAT-TODO-MARKER                    LOW      DEAD_CODE         -
CHM-JAVA-NAT-DEBUG-RESIDUE                  LOW      DEAD_CODE         inside main(); path under test/
CHM-JAVA-NAT-DUPLICATE-BLOCK                MEDIUM   DUPLICATION       blocks without branches shorter than 120
                                                                      tokens; getter/setter; equals/hashCode/
                                                                      toString; switch-case constant tables;
                                                                      pure field-assignment sequences
CHM-JAVA-NAT-DUPLICATE-BUSINESS-RULE        MEDIUM   DUPLICATION       only 2 occurrences; plain null checks
CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE          MEDIUM   WRONG_ABSTRACTION @FeignClient/@Mapper/@Service (ABS-003/005);
                                                                      >=2 implementations; >=2 injection points;
                                                                      packages api/spi/client/remote (downgraded to
                                                                      LOW + needs manual confirmation)
CHM-JAVA-NAT-SINGLE-CALL-WRAPPER            MEDIUM   WRONG_ABSTRACTION exception translation, validation, logging,
                                                                      @Transactional, retry/circuit breaker, third
                                                                      party SDK isolation (ABS-003)
CHM-JAVA-NAT-SPECULATIVE-FACTORY            MEDIUM   OVER_ENGINEERING  >=2 implementations or >=2 registrations
CHM-JAVA-NAT-UNUSED-CONFIG-KEY              LOW      CONFIG_INFLATION  @Value with a default value
CHM-JAVA-NAT-COMPAT-JUNK                    LOW      COMPATIBILITY_JUNK @Deprecated present (explicit contract);
                                                                      identifier named in CHANGELOG
CHM-JAVA-NAT-LARGE-METHOD                   MEDIUM/LOW LARGE_METHOD    long + low complexity stays LOW (CPLX-003)
CHM-JAVA-NAT-DEEP-NESTING                   MEDIUM   COMPLEXITY        -
CHM-JAVA-NAT-CYCLOMATIC                     MEDIUM   COMPLEXITY        -
CHM-JAVA-NAT-LARGE-CLASS                    LOW      LARGE_CLASS       -
CHM-JAVA-NAT-LONG-PARAM-LIST                LOW      COMPLEXITY        constructors; @Builder classes; *Mapper
CHM-JAVA-NAT-EMPTY-CATCH                    HIGH/LOW ERROR_HANDLING    throw/log/counter/meter inside (ERR-003);
                                                                      downgraded to LOW (never suppressed) when
                                                                      the catch is annotated (comment / ignore
                                                                      wording), when the try body only probes /
                                                                      parses / cleans up (Class.forName,
                                                                      getResourceAsStream, Files.delete*,
                                                                      close(), Thread.sleep, System.getenv) or
                                                                      when the parameter is named
                                                                      ignored/_/unused (the Java idiom for
                                                                      "intentionally unused")
CHM-JAVA-NAT-CATCH-RETURN-NULL              HIGH     ERROR_HANDLING    Optional return; name ends OrNull/Safe/Try
CHM-JAVA-NAT-SWALLOW-AND-SUCCESS            HIGH     ERROR_HANDLING    -
CHM-JAVA-NAT-GENERIC-CATCH                  LOW      ERROR_HANDLING    Controller/Advice/Filter/Interceptor/Job
CHM-JAVA-NAT-RETRY-AMPLIFY                  HIGH     ERROR_HANDLING    maxAttempts/maxRetries/backoff/@Backoff
CHM-JAVA-NAT-UNCLOSED-RESOURCE              HIGH     RESOURCE_SAFETY   try-with-resources (RES-002); finally close;
                                                                      factory return
CHM-JAVA-NAT-EXECUTOR-PER-CALL              HIGH     RESOURCE_SAFETY   static final field; constructor;
                                                                      @PostConstruct; singleton field assignment
CHM-JAVA-NAT-THREADPOOL-NO-SHUTDOWN         LOW      RESOURCE_SAFETY   repository contains shutdown()/@PreDestroy
                                                                      /DisposableBean (RES-003 wording enforced)
CHM-JAVA-NAT-SHARED-MUTABLE                 HIGH     CONCURRENCY       ConcurrentHashMap/CopyOnWriteArrayList/
                                                                      AtomicXxx/volatile (CON-002); final assigned
                                                                      only in the constructor; @Scope prototype
CHM-JAVA-NAT-SEMAPHORE-LEAK                 HIGH     CONCURRENCY       release() in finally
CHM-JAVA-NAT-LOCK-REMOTE-CALL               HIGH     CONCURRENCY       -
CHM-JAVA-NAT-DOUBLE-CHECK-NO-VOLATILE       HIGH     CONCURRENCY       field declared volatile
CHM-JAVA-NAT-NO-IDEMPOTENCY                 MEDIUM/HIGH CONCURRENCY    idempotent/requestId/traceId/bizNo/orderNo
CHM-JAVA-NAT-NPLUS1                         HIGH     DATABASE          batch prefetch selectBatchIds/in (...) /
                                                                      selectList(ids) (DB-002); constant bound <=10
                                                                      (downgraded to LOW)
CHM-JAVA-NAT-UPDATE-NO-WHERE                CRITICAL DATABASE          -
CHM-JAVA-NAT-DELETE-NO-WHERE                CRITICAL DATABASE          -
CHM-JAVA-NAT-TX-REMOTE-CALL                 HIGH     DATABASE          -
CHM-JAVA-NAT-SELECT-STAR                    LOW      DATABASE          statement carries LIMIT
CHM-JAVA-NAT-UNBOUNDED-IN                   MEDIUM   DATABASE          subList/limit/PageHelper guard present
CHM-JAVA-NAT-DUP-SQL                        MEDIUM   DATABASE          fewer than 3 mapper/XML sites
CHM-JAVA-NAT-ON2                            MEDIUM   PERFORMANCE       containsKey on a Map (PERF-002); collection
                                                                      literal <= 10 elements; never HIGH
                                                                      without a benchmark (PERF-001)
CHM-JAVA-NAT-REPEAT-SERIALIZE               MEDIUM   PERFORMANCE       different target objects
CHM-JAVA-NAT-HARDCODED-TIME                 MEDIUM   TESTABILITY       injectable Clock/LocalDate (TEST-002);
                                                                      TimeUtils.now()/DateUtil.now(); <= 2 calls
CHM-JAVA-NAT-GLOBAL-MUTABLE-SINGLETON       MEDIUM   TESTABILITY       static final constants / immutable types
------------------------------------------------------------------------------
CHM-JAVA-NAT-NO-CACHE-HIGH-FREQ is intentionally NOT implemented: spec
CHM-PERF-004 forbids reporting "there is no cache" as a problem.  See the
comment on ``_rule_no_cache_not_implemented`` at the bottom of this module.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from ..contracts import (
    ChangeKind,
    EvidenceProvider,
    Language,
    ProviderResult,
    ScanContext,
)
from ..errors import ToolFailureKind, ToolError, ToolStatus
from ..schema import Category, EvidenceKind, PerfConfidence, RawFinding, Severity
from ..util import iter_files, read_text, strip_comments_and_strings

PROVIDER_NAME = "native-java"

MAX_FILE_BYTES = 2 * 1024 * 1024
#: hard bound on the repo-wide duplication token corpus (deterministic order)
MAX_DUP_FILES = 1200
MAX_DUP_TOKENS = 1_500_000
DUP_WINDOW = 40
DUP_STEP = 10
MAX_FINDINGS_PER_RULE_PER_FILE = 40

TEST_PATH_RE = re.compile(r"(?:^|/)(?:test|tests|src/test|__tests__)(?:/|$)", re.I)

DEFAULT_COMPLEXITY = {
    "method_lines": 80,
    "method_cyclomatic": 15,
    "class_lines": 800,
    "nesting_depth": 4,
}
DEFAULT_DUP_MIN_TOKENS = 100

# --------------------------------------------------------------------------
# compiled patterns
# --------------------------------------------------------------------------

_MODS = r"(?:(?:public|private|protected|static|final|synchronized|abstract|native|default|strictfp|transient|volatile)\s+)*"
_ANN = r"(?:@(?!interface\b)[\w$.]+(?:\s*\([^()]*\))?\s*)*"

_METHOD_HEAD_RE = re.compile(
    r"^" + _ANN + r"(?P<mods>" + _MODS + r")"
    r"(?:<[^<>{};()]*>\s*)?"
    r"(?P<ret>[A-Za-z_$][\w$.]*(?:\s*<[^<>{};()]*>)?(?:\s*\[\s*\])*)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*"
    r"\((?P<params>[^(){};]*)\)\s*"
    r"(?:throws\s+[\w$.,\s]+?)?"
    r"(?P<tail>[{;]?)"
    r".*$"
)

_CTOR_HEAD_RE = re.compile(
    r"^" + _ANN + r"(?P<mods>(?:(?:public|private|protected)\s+)*)"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*"
    r"\((?P<params>[^(){};]*)\)\s*"
    r"(?:throws\s+[\w$.,\s]+?)?"
    r"(?P<tail>[{;]?)"
    r".*$"
)

_CLASS_HEAD_RE = re.compile(
    r"^" + _ANN + r"(?P<mods>(?:(?:public|private|protected|static|final|abstract|sealed|non-sealed|strictfp)\s+)*)"
    r"(?P<kind>class|interface|enum|record)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)"
    r"(?P<rest>[^{;]*?)"
    r"(?P<tail>\{?)\s*$"
)

_FIELD_RE = re.compile(
    r"^" + _ANN + r"(?P<mods>" + _MODS + r")"
    r"(?P<type>[A-Za-z_$][\w$.]*(?:\s*<[^<>{};()]*>)?(?:\s*\[\s*\])*)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*(?:=[^;]*)?;\s*$"
)

_RESERVED_RET = frozenset(
    """
    return new throw if for while switch catch do else try assert synchronized
    break continue case default instanceof yield this super import package
    """.split()
)

#: A leading modifier can never be a return type; without this guard
#: ``public Foo(int a, ...)`` would parse as a method returning ``public``.
_MODIFIER_WORDS = frozenset(
    """
    public private protected static final synchronized abstract native default
    strictfp transient volatile
    """.split()
)

_CATCH_ANY_RE = re.compile(r"\bcatch\s*\(")
_LOOP_ANY_RE = re.compile(r"\b(?:for|while)\s*\(|\bdo\s*\{")
_SYNC_ANY_RE = re.compile(r"\bsynchronized\s*\(")

#: catch parameters whose *variable name* says "I deliberately ignore this".
_JAVA_UNUSED_BINDING_RE = re.compile(
    r"^(?:_+|_(?:e|ex|err|exception|ignored|unused|t|x)"
    r"|ignored|ignore|unused)$",
    re.I,
)

#: Calls whose failure is idiomatic to ignore: probing for something optional,
#: parsing a value that has a fallback, or best-effort cleanup.  A swallowed
#: error around one of these is downgraded, never suppressed.
_JAVA_PROBE_CALL_RE = re.compile(
    r"(?:"
    r"\bClass\s*\.\s*forName\s*\("
    r"|\bFiles\s*\.\s*(?:delete|deleteIfExists|exists|notExists|isReadable"
    r"|isWritable|isExecutable|isDirectory|isRegularFile)\s*\("
    r"|\bThread\s*\.\s*sleep\s*\("
    r"|\bSystem\s*\.\s*get(?:Property|env)\s*\("
    r"|\.\s*(?:getResourceAsStream|getResource|deleteIfExists|delete|close"
    r"|shutdownNow|shutdown|getProperty)\s*\("
    r")"
)

_IF_PAREN_RE = re.compile(r"\bif\s*\(")
_UNREACHABLE_RE = re.compile(r"\b(?:if|while)\s*\(\s*(?:false|true)\s*\)")
_DEBUG_RE = re.compile(r"\bSystem\s*\.\s*(?:out|err)\s*\.\s*print|\.printStackTrace\s*\(")
_TODO_RE = re.compile(r"(?://|/\*|\*)[^\n]*\b(TODO|FIXME|XXX|HACK)\b")
_BRANCH_TOKENS = frozenset({"if", "for", "while", "switch", "catch", "do", "&&", "||", "?"})

_TOKEN_RE = re.compile(
    r"(?P<comment>//[^\n]*|/\*.*?\*/)"
    r"|(?P<str>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
    r"|(?P<num>\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?[fFdDlL]?)"
    r"|(?P<id>[A-Za-z_$][A-Za-z0-9_$]*)"
    r"|(?P<sym>[^\s])",
    re.S,
)

_IDENT_RE = re.compile(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\b")
_STRING_LIT_RE = re.compile(r"\"((?:\\.|[^\"\\])*)\"")
_ANNOTATION_NAME_RE = re.compile(r"@([\w$.]+)")

_CAMEL_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])|[0-9]+")

_CYCLO_RE = re.compile(r"\b(?:if|for|while|case|catch)\b")

_VALUE_RE = re.compile(r"@Value\s*\(\s*\"\$\{([^}:]+)(?::([^}]*))?\}\"\s*\)")
_CONFIG_PROPS_RE = re.compile(r"@ConfigurationProperties\s*\(\s*(?:prefix\s*=\s*)?\"([^\"]+)\"")

_RETRY_RE = re.compile(r"@(Retryable|Retry|Recover|CircuitBreaker)\b")
_RETRY_BOUND_RE = re.compile(r"maxAttempts|maxRetries|maxRetry|attempts\s*[<>=]|@Backoff|backoff|max_retry", re.I)

_RESOURCE_CTORS = (
    "FileInputStream",
    "FileOutputStream",
    "FileReader",
    "FileWriter",
    "BufferedReader",
    "BufferedWriter",
    "InputStreamReader",
    "OutputStreamWriter",
    "RandomAccessFile",
    "Socket",
    "ServerSocket",
    "Scanner",
    "PrintWriter",
)
_RESOURCE_NEW_RE = re.compile(r"\bnew\s+(" + "|".join(_RESOURCE_CTORS) + r")\s*\(")

_EXECUTOR_RE = re.compile(
    r"\bExecutors\s*\.\s*(newFixedThreadPool|newCachedThreadPool|newSingleThreadExecutor"
    r"|newScheduledThreadPool|newWorkStealingPool)\s*\(|\bnew\s+Thread\s*\(|\bnew\s+ThreadPoolExecutor\s*\("
)
_POOL_SHUTDOWN_RE = re.compile(r"\.shutdown\s*\(|@PreDestroy|DisposableBean|\.shutdownNow\s*\(")

_SAFE_COLLECTIONS = (
    "ConcurrentHashMap",
    "ConcurrentLinkedQueue",
    "ConcurrentLinkedDeque",
    "CopyOnWriteArrayList",
    "CopyOnWriteArraySet",
    "ConcurrentSkipListMap",
    "ConcurrentSkipListSet",
    "AtomicInteger",
    "AtomicLong",
    "AtomicBoolean",
    "AtomicReference",
    "BlockingQueue",
    "LinkedBlockingQueue",
    "ArrayBlockingQueue",
)
_UNSAFE_COLLECTIONS = (
    "HashMap",
    "HashSet",
    "ArrayList",
    "LinkedList",
    "TreeMap",
    "TreeSet",
    "LinkedHashMap",
    "LinkedHashSet",
    "StringBuilder",
    "StringBuffer",
    "Vector",
)
_UNSAFE_COLL_RE = re.compile(r"\b(" + "|".join(_UNSAFE_COLLECTIONS) + r")\b")

_SCOPE_RE = re.compile(r"@Scope\s*\(\s*\"(prototype|request|session)\"\s*\)")

_REMOTE_CALL_RE = re.compile(
    r"\brestTemplate\s*\.|\bhttpClient\s*\.|\bwebClient\s*\.|\bfeign\w*\s*\."
    r"|\b\w+Client\s*\.\s*\w+\s*\(|\.\s*(?:getForObject|postForObject|exchange|execute)\s*\("
    r"|\bjdbcTemplate\s*\.|\bmapper\s*\.|\bkafkaTemplate\s*\.|\brocketMQTemplate\s*\.|\bamqpTemplate\s*\."
    r"|\b\w+Service\s*\.\s*(?:pay|refund|transfer|send|notify)\s*\("
)

_DB_CALL_RE = re.compile(
    r"\.\s*(?:selectById|selectOne|selectList|selectByMap|query|queryForObject|queryForList"
    r"|getById|findById|findOne|findAll|count)\s*\("
    r"|\bmapper\s*\.\s*\w+\s*\("
)
_DB_BATCH_RE = re.compile(r"selectBatchIds|selectList\s*\(|Batch|batch|\.in\s*\(|in\s*\(")

_SERIALIZE_RE = re.compile(
    r"(?:JSON\s*\.\s*toJSONString|JSONObject\s*\.\s*toJSONString"
    r"|objectMapper\s*\.\s*writeValueAsString|JSON\s*\.\s*toJSONBytes)\s*\(\s*([^(),]+?)\s*[,)]"
)

_TIME_CALL_RE = re.compile(
    r"\bLocalDateTime\s*\.\s*now\s*\(|\bLocalDate\s*\.\s*now\s*\(|\bLocalTime\s*\.\s*now\s*\("
    r"|\bSystem\s*\.\s*currentTimeMillis\s*\(|\bnew\s+Date\s*\(\s*\)|\bInstant\s*\.\s*now\s*\("
)
_CLOCK_SUPPRESS_RE = re.compile(r"\bClock\b|TimeUtils\s*\.\s*now|DateUtil\s*\.\s*now|DateTimeUtils\s*\.\s*now")

_SQL_STMT_RE = re.compile(r"^\s*(select|update|delete|insert)\b", re.I)
_SQL_UPDATE_RE = re.compile(r"\bupdate\s+[`\"\w.]+\s+set\b", re.I)
_SQL_DELETE_RE = re.compile(r"\bdelete\s+from\b", re.I)
_SQL_WHERE_RE = re.compile(r"\bwhere\b", re.I)
_SQL_LIMIT_RE = re.compile(r"\blimit\b", re.I)
_SQL_IN_RE = re.compile(r"\bin\s*\(\s*[^)]*\)", re.I)
_SQL_BOUND_RE = re.compile(r"subList|limit|PageHelper|pageSize|MAX_IN|maxSize|\.stream\(\)\.limit", re.I)
_SQL_PLACEHOLDER_RE = re.compile(r"#\{[^}]*\}|\$\{[^}]*\}|\?")

_XML_STMT_RE = re.compile(
    r"<(select|update|delete|insert)\b[^>]*\bid\s*=\s*\"([^\"]*)\"[^>]*>(.*?)</\1>",
    re.S | re.I,
)
_XML_WHERE_RE = re.compile(r"<\s*where\b|\bwhere\b", re.I)
_XML_DYNAMIC_TAG_RE = re.compile(r"<if\b|<foreach\b|<trim\b|<set\b|<choose\b", re.I)

_PKG_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)

_SPI_BOUNDARY_RE = re.compile(
    r"@(?:FeignClient|Mapper|DubboService|DubboReference|RemoteService|HttpExchange)\b"
)

_IDEMPOTENT_RE = re.compile(
    r"idempotent|requestId|traceId|bizNo|orderNo|@Idempotent|uniqueKey|dedup", re.I
)
_WRITE_RE = re.compile(
    r"\.\s*(?:insert|save|update|delete|batchInsert|saveOrUpdate|insertOrUpdate)\s*\(|\bmapper\s*\."
)
_SIDE_EFFECT_RE = re.compile(
    r"\brestTemplate\s*\.|\bhttpClient\s*\.|\bfeign\w*\s*\.|\bkafkaTemplate\s*\."
    r"|\brocketMQTemplate\s*\.|\bamqpTemplate\s*\.|\b\w+Producer\s*\.\s*send\s*\("
    r"|\bpay\w*\s*\.|\brefund\w*\s*\.|\.\s*(?:pay|refund)\s*\("
)
_MONEY_RE = re.compile(r"amount|money|price|refund|pay\b|金额|退款", re.I)

_COMPAT_WORDS = frozenset({"legacy", "deprecated", "old", "v1", "compat", "fallback", "temp", "tmp"})

_CTRL_KEYWORDS = frozenset({"if", "for", "while", "switch", "catch", "synchronized"})
_CTRL_BLOCK_KEYWORDS = frozenset({"else", "do", "try", "finally"})

_JAVA_KEYWORDS = frozenset(
    """
    abstract assert boolean break byte case catch char class const continue default do double
    else enum extends final finally float for goto if implements import instanceof int interface
    long native new package private protected public return short static strictfp super switch
    synchronized this throw throws transient try void volatile while true false null record var
    yield sealed permits non-sealed
    """.split()
)


# --------------------------------------------------------------------------
# text / structure helpers
# --------------------------------------------------------------------------


def _split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _strip_comments_only(code: str) -> str:
    """Remove comments, keep string literals and the original line count."""
    out: list[str] = []
    i = 0
    n = len(code)
    in_str: Optional[str] = None
    in_line = False
    in_block = False
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if in_line:
            if ch == "\n":
                in_line = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(code[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _depth_profile(skel_lines: list[str]) -> tuple[list[int], list[int]]:
    start = [0] * len(skel_lines)
    end = [0] * len(skel_lines)
    depth = 0
    for i, line in enumerate(skel_lines):
        start[i] = depth
        for ch in line:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        end[i] = depth
    return start, end


def _block_end(start: list[int], end: list[int], open_line: int) -> int:
    if open_line >= len(end):
        return open_line
    base = start[open_line]
    if end[open_line] <= base:
        return open_line
    for j in range(open_line + 1, len(end)):
        if end[j] == base:
            return j
    return len(end) - 1


def _find_open_line(
    skel_lines: list[str],
    start: list[int],
    end: list[int],
    head_end: int,
    max_extra: int = 6,
) -> Optional[int]:
    if head_end < len(end) and end[head_end] > start[head_end]:
        return head_end
    for k in range(head_end + 1, min(head_end + 1 + max_extra, len(skel_lines))):
        stripped = skel_lines[k].strip()
        if stripped == "":
            continue
        if stripped.startswith(("{", "extends", "implements", "throws", "<", ",")):
            if end[k] > start[k]:
                return k
            continue
        return None
    return None


def _logical_headers(skel_lines: list[str]) -> dict[int, tuple[str, int]]:
    """Map start line -> (joined header text, last line of the header)."""
    out: dict[int, tuple[str, int]] = {}
    i = 0
    n = len(skel_lines)
    while i < n:
        line = skel_lines[i]
        if line.count("(") > line.count(")"):
            buf = line
            j = i
            guard = 0
            while j + 1 < n and buf.count("(") > buf.count(")") and guard < 30:
                j += 1
                guard += 1
                buf = buf + " " + skel_lines[j]
            out[i] = (" ".join(buf.split()), j)
            i = j + 1
            continue
        out[i] = (" ".join(line.split()), i)
        i += 1
    return out


def _annotations_above(noc_lines: list[str], line_index: int) -> list[tuple[int, str]]:
    """Collect contiguous annotations directly above ``line_index``."""
    collected: list[tuple[int, str]] = []
    j = line_index - 1
    while j >= 0:
        stripped = noc_lines[j].strip()
        if stripped == "":
            k = j - 1
            while k >= 0 and noc_lines[k].strip() == "":
                k -= 1
            if k >= 0 and noc_lines[k].strip().startswith("@"):
                j = k
                continue
            break
        if stripped.startswith("@"):
            text = stripped
            begin = j
            guard = 0
            while text.count("(") > text.count(")") and begin - 1 >= 0 and guard < 20:
                begin -= 1
                guard += 1
                text = noc_lines[begin].strip() + " " + text
            collected.append((begin, " ".join(text.split())))
            j = begin - 1
            continue
        break
    collected.reverse()
    return collected


def _annotation_names(annotations: Iterable[tuple[int, str]]) -> list[str]:
    names: list[str] = []
    for _line, text in annotations:
        for m in _ANNOTATION_NAME_RE.finditer(text):
            names.append(m.group(1).split(".")[-1])
    return names


def _split_params(params: str) -> list[str]:
    if not params.strip():
        return []
    out: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in params:
        if ch in "<([{":
            depth += 1
        elif ch in ">)]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        out.append(tail)
    return out


def _cyclomatic(body: str) -> int:
    value = 1
    value += len(_CYCLO_RE.findall(body))
    value += body.count("&&") + body.count("||")
    value += len(re.findall(r"(?<!<)\?", body))
    return value


def _looks_like_control_brace(text: str, index: int) -> bool:
    j = index - 1
    while j >= 0 and text[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return False
    if text[j] == ")":
        depth = 1
        k = j - 1
        while k >= 0 and depth > 0:
            if text[k] == ")":
                depth += 1
            elif text[k] == "(":
                depth -= 1
            k -= 1
        while k >= 0 and text[k] in " \t\r\n":
            k -= 1
        end = k + 1
        while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
            k -= 1
        return text[k + 1 : end] in _CTRL_KEYWORDS
    end = j + 1
    k = j
    while k >= 0 and (text[k].isalnum() or text[k] in "_$-"):
        k -= 1
    return text[k + 1 : end] in _CTRL_BLOCK_KEYWORDS


def _max_control_nesting(body: str) -> int:
    stack: list[bool] = []
    ctrl = 0
    maxd = 0
    for i, ch in enumerate(body):
        if ch == "{":
            is_ctrl = _looks_like_control_brace(body, i)
            stack.append(is_ctrl)
            if is_ctrl:
                ctrl += 1
                if ctrl > maxd:
                    maxd = ctrl
        elif ch == "}":
            if stack:
                if stack.pop():
                    ctrl -= 1
    return maxd


def _paren_match(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _brace_match(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _brace_match_back(text: str, close_idx: int) -> int:
    depth = 0
    i = close_idx
    while i >= 0:
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                return i
        i -= 1
    return -1


def _enclosing_try(text: str, catch_start: int) -> Optional[tuple[int, int]]:
    """``(try_open_brace, try_close_brace)`` for the ``try`` owning this catch."""
    i = catch_start - 1
    while i >= 0 and text[i] in " \t\r\n":
        i -= 1
    if i < 0 or text[i] != "}":
        return None
    open_idx = _brace_match_back(text, i)
    if open_idx < 0:
        return None
    j = open_idx - 1
    while j >= 0 and text[j] in " \t\r\n":
        j -= 1
    end = j + 1
    while j >= 0 and (text[j].isalnum() or text[j] in "_$"):
        j -= 1
    if text[j + 1 : end] != "try":
        return None
    return open_idx, i


def _comment_only(blob: str) -> bool:
    """True when a raw source region holds nothing but whitespace/comments."""
    return not re.sub(r"//[^\n]*|/\*.*?\*/", " ", blob, flags=re.S).strip()


def _line_starts(text: str) -> list[int]:
    """Offset of the first character of every line (same shape as ``_JavaFile``)."""
    starts = [0]
    idx = text.find("\n")
    while idx >= 0:
        starts.append(idx + 1)
        idx = text.find("\n", idx + 1)
    return starts


def _aligned_skeleton(code: str) -> str:
    """Comments + string literals blanked, **every offset preserved**.

    ``util.strip_comments_and_strings`` drops the two delimiter characters of
    every comment, so a skeleton offset does not index the original source.
    Rules that must read the raw text through a skeleton offset (the empty
    catch rule needs the real body to tell "no statement" from "comment") use
    this instead.  Length and newline positions are identical to ``code``.
    """
    out = list(code)
    i = 0
    n = len(code)
    quote: Optional[str] = None
    while i < n:
        ch = code[i]
        if quote is not None:
            if ch == "\\":
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
                continue
            if ch == quote:
                quote = None
            if ch != "\n":
                out[i] = " "
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out[i] = " "
            i += 1
            continue
        if ch == "/" and i + 1 < n and code[i + 1] == "/":
            while i < n and code[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if ch == "/" and i + 1 < n and code[i + 1] == "*":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n:
                if code[i] == "*" and i + 1 < n and code[i + 1] == "/":
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    break
                if code[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def _tokenize(text: str) -> tuple[list[str], list[int]]:
    tokens: list[str] = []
    lines: list[int] = []
    newlines = [m.start() for m in re.finditer("\n", text)]
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        if kind == "comment":
            continue
        value = m.group()
        if kind == "id":
            token = value if value in _JAVA_KEYWORDS else "ID"
        elif kind == "num":
            token = "NUM"
        elif kind == "str":
            token = "STR"
        else:
            token = value
        tokens.append(token)
        lines.append(bisect.bisect_right(newlines, m.start()) + 1)
    return tokens, lines


def _camel_words(name: str) -> list[str]:
    return [w.lower() for w in _CAMEL_RE.findall(name)]


# --------------------------------------------------------------------------
# parsed model
# --------------------------------------------------------------------------


@dataclass
class _JavaMethod:
    name: str
    mods: str
    ret: str
    params: list[str]
    annotations: list[tuple[int, str]]
    decl_line: int
    open_line: int
    close_line: int
    class_name: Optional[str]
    is_ctor: bool = False
    has_body: bool = True
    #: body text for single-line declarations (`void f() { doIt(); }`)
    inline_body: str = ""

    @property
    def is_abstract(self) -> bool:
        return not self.has_body

    def body_text(self, skel_lines: list[str]) -> str:
        if self.inline_body:
            return self.inline_body
        if self.open_line >= self.close_line:
            return ""
        return "\n".join(skel_lines[self.open_line + 1 : self.close_line])

    def body_line_count(self) -> int:
        if self.inline_body:
            return 1
        return max(0, self.close_line - self.open_line - 1)


@dataclass
class _JavaField:
    name: str
    type: str
    mods: str
    annotations: list[tuple[int, str]]
    line: int
    class_name: Optional[str]


@dataclass
class _JavaClass:
    name: str
    kind: str
    mods: str
    annotations: list[tuple[int, str]]
    decl_line: int
    open_line: int
    close_line: int
    rest: str
    methods: list[_JavaMethod] = field(default_factory=list)
    fields: list[_JavaField] = field(default_factory=list)

    @property
    def body_depth(self) -> int:
        return self.open_line


@dataclass
class _JavaFile:
    path: str
    raw_lines: list[str]
    skel_lines: list[str]
    noc_lines: list[str]
    start_depth: list[int]
    end_depth: list[int]
    classes: list[_JavaClass]
    methods: list[_JavaMethod]
    fields: list[_JavaField]
    skel_text: str = ""
    #: original source; the offset-preserving skeleton (``_aligned_skeleton``)
    #: shares its offsets, so ``skel_text``-derived offsets must NOT index this
    raw_text: str = ""
    line_starts: list[int] = field(default_factory=list)

    def line_index(self, offset: int) -> int:
        """0-based line index for a character offset into ``skel_text``."""
        return bisect.bisect_right(self.line_starts, offset) - 1

    def method_at(self, line: int) -> Optional[_JavaMethod]:
        best: Optional[_JavaMethod] = None
        for m in self.methods:
            if m.open_line <= line <= m.close_line:
                if best is None or m.open_line >= best.open_line:
                    best = m
        return best

    def class_at(self, line: int) -> Optional[_JavaClass]:
        best: Optional[_JavaClass] = None
        for c in self.classes:
            if c.open_line <= line <= c.close_line:
                if best is None or c.open_line >= best.open_line:
                    best = c
        return best


@dataclass
class _CatchSpan:
    """One ``catch`` clause located by character offset."""

    head_line: int  # 0-based line of the `catch` keyword
    open_line: int  # 0-based line of the `{`
    close_line: int  # 0-based line of the `}`
    param: str  # `Exception e` / `A | B e` (parentheses stripped)
    body: str  # skeleton text between the braces
    open_offset: int
    close_offset: int
    keyword_offset: int


def _parse_java(path: str, text: str) -> _JavaFile:
    raw_lines = _split_lines(text)
    skel_text = strip_comments_and_strings(text)
    skel_lines = _split_lines(skel_text)
    noc_lines = _split_lines(_strip_comments_only(text))
    width = max(len(raw_lines), len(skel_lines), len(noc_lines))
    for bucket in (raw_lines, skel_lines, noc_lines):
        while len(bucket) < width:
            bucket.append("")
    start, end = _depth_profile(skel_lines)
    logical = _logical_headers(skel_lines)
    line_starts: list[int] = []
    cursor = 0
    for line in skel_lines:
        line_starts.append(cursor)
        cursor += len(line) + 1

    classes: list[_JavaClass] = []
    for i in sorted(logical):
        head, head_end = logical[i]
        cm = _CLASS_HEAD_RE.match(head)
        if cm is None:
            continue
        open_line = _find_open_line(skel_lines, start, end, head_end, max_extra=8)
        if open_line is None:
            continue
        close_line = _block_end(start, end, open_line)
        classes.append(
            _JavaClass(
                name=cm.group("name"),
                kind=cm.group("kind"),
                mods=cm.group("mods"),
                annotations=_annotations_above(noc_lines, i),
                decl_line=i,
                open_line=open_line,
                close_line=close_line,
                rest=cm.group("rest") or "",
            )
        )

    methods: list[_JavaMethod] = []
    for i in sorted(logical):
        head, head_end = logical[i]
        mm = _METHOD_HEAD_RE.match(head)
        if mm is not None and (
            mm.group("ret") in _RESERVED_RET or mm.group("ret") in _MODIFIER_WORDS
        ):
            mm = None
        is_ctor = False
        if mm is not None:
            name = mm.group("name")
            mods = mm.group("mods") or ""
            ret = mm.group("ret")
            params = _split_params(mm.group("params"))
            tail = mm.group("tail")
        else:
            cm = _CTOR_HEAD_RE.match(head)
            if cm is None:
                continue
            name = cm.group("name")
            mods = cm.group("mods") or ""
            ret = ""
            params = _split_params(cm.group("params"))
            tail = cm.group("tail")
            is_ctor = True
            if _CLASS_HEAD_RE.match(head) is not None:
                continue

        open_line: Optional[int]
        inline_body = ""
        if tail == ";":
            open_line = i
            close_line = i
        else:
            open_line = _find_open_line(skel_lines, start, end, head_end, max_extra=4)
            if open_line is None and "{" in head:
                # single-line body: `void f() { doIt(); }`
                open_line = head_end
                close_line = head_end
                line_text = skel_lines[head_end]
                brace_open = line_text.find("{")
                brace_close = line_text.rfind("}")
                if brace_open >= 0 and brace_close > brace_open:
                    inline_body = line_text[brace_open + 1 : brace_close]
            elif open_line is None:
                continue
            else:
                close_line = _block_end(start, end, open_line)

        methods.append(
            _JavaMethod(
                name=name,
                mods=mods,
                ret=ret,
                params=params,
                annotations=_annotations_above(noc_lines, i),
                decl_line=i,
                open_line=open_line,
                close_line=close_line,
                class_name=None,
                is_ctor=is_ctor,
                has_body=(tail != ";"),
                inline_body=inline_body,
            )
        )

    # assign the innermost enclosing class
    for m in methods:
        owner: Optional[_JavaClass] = None
        for c in classes:
            if c.open_line <= m.open_line <= c.close_line:
                if owner is None or c.open_line >= owner.open_line:
                    owner = c
        m.class_name = owner.name if owner else None

    fields: list[_JavaField] = []
    for c in classes:
        body_depth = start[c.open_line] + 1
        for i in range(c.open_line + 1, min(c.close_line, len(skel_lines))):
            if start[i] != body_depth:
                continue
            fm = _FIELD_RE.match(logical.get(i, ("", i))[0])
            if fm is None:
                continue
            if fm.group("name") in _JAVA_KEYWORDS:
                continue
            fields.append(
                _JavaField(
                    name=fm.group("name"),
                    type=fm.group("type"),
                    mods=fm.group("mods") or "",
                    annotations=_annotations_above(noc_lines, i),
                    line=i,
                    class_name=c.name,
                )
            )

    for c in classes:
        c.methods = [m for m in methods if c.open_line <= m.open_line <= c.close_line]
        c.fields = [f for f in fields if f.class_name == c.name and c.open_line < f.line < c.close_line]

    return _JavaFile(
        path=path,
        raw_lines=raw_lines,
        skel_lines=skel_lines,
        noc_lines=noc_lines,
        start_depth=start,
        end_depth=end,
        classes=classes,
        methods=methods,
        fields=fields,
        skel_text=skel_text,
        raw_text=text,
        line_starts=line_starts,
    )


# --------------------------------------------------------------------------
# repo index
# --------------------------------------------------------------------------


@dataclass
class _ClassDecl:
    path: str
    name: str
    kind: str
    implements: list[str]
    line: int


class _RepoIndex:
    """Deterministic, lazily built repo-wide index used by cross-file rules."""

    def __init__(self, ctx: ScanContext) -> None:
        self.ctx = ctx
        self.root = Path(ctx.repo_root)
        self._java_paths: Optional[list[str]] = None
        self._side_paths: Optional[list[str]] = None
        self.texts: dict[str, str] = {}
        self.noc_texts: dict[str, str] = {}
        self._side_texts: dict[str, str] = {}
        self._ident_counts: Optional[dict[str, int]] = None
        self._string_literals: Optional[set[str]] = None
        self._class_decls: Optional[list[_ClassDecl]] = None
        self._tokens: dict[str, tuple[list[str], list[int]]] = {}
        self._token_budget = MAX_DUP_TOKENS
        self._changelog: Optional[str] = None

    # ------------------------------------------------------------ loading

    def _excludes(self) -> list[str]:
        configured = getattr(self.ctx.config, "excludes", None)
        if configured:
            return list(configured)
        from ..util import DEFAULT_EXCLUDES

        return list(DEFAULT_EXCLUDES)

    def java_paths(self) -> list[str]:
        if self._java_paths is None:
            if self.ctx.repo_files:
                rels = sorted({p.replace("\\", "/") for p in self.ctx.repo_files})
                self._java_paths = [p for p in rels if p.lower().endswith(".java")]
            else:
                self._java_paths = sorted(
                    p.resolve().relative_to(self.root.resolve()).as_posix()
                    if str(p).startswith(str(self.root))
                    else p.as_posix()
                    for p in iter_files(
                        self.root, suffixes=[".java"], excludes=self._excludes()
                    )
                )
        return self._java_paths

    def side_paths(self) -> list[str]:
        if self._side_paths is None:
            suffixes = [".xml", ".properties", ".yml", ".yaml"]
            if self.ctx.repo_files:
                rels = sorted({p.replace("\\", "/") for p in self.ctx.repo_files})
                self._side_paths = [p for p in rels if p.lower().endswith(tuple(suffixes))]
            else:
                self._side_paths = sorted(
                    p.resolve().relative_to(self.root.resolve()).as_posix()
                    if str(p).startswith(str(self.root))
                    else p.as_posix()
                    for p in iter_files(self.root, suffixes=suffixes, excludes=self._excludes())
                )
        return self._side_paths

    def java_text(self, rel: str) -> str:
        if rel not in self.texts:
            self.texts[rel] = read_text(self.root / rel, max_bytes=MAX_FILE_BYTES)
        return self.texts[rel]

    def noc_text(self, rel: str) -> str:
        if rel not in self.noc_texts:
            self.noc_texts[rel] = _strip_comments_only(self.java_text(rel))
        return self.noc_texts[rel]

    def side_text(self, rel: str) -> str:
        if rel not in self._side_texts:
            self._side_texts[rel] = read_text(self.root / rel, max_bytes=MAX_FILE_BYTES)
        return self._side_texts[rel]

    # ------------------------------------------------------------ derived

    def ident_counts(self) -> dict[str, int]:
        if self._ident_counts is None:
            counts: dict[str, int] = {}
            for rel in self.java_paths():
                for m in _IDENT_RE.finditer(self.noc_text(rel)):
                    token = m.group(1)
                    counts[token] = counts.get(token, 0) + 1
            for rel in self.side_paths():
                for m in _IDENT_RE.finditer(self.side_text(rel)):
                    token = m.group(1)
                    counts[token] = counts.get(token, 0) + 1
            self._ident_counts = counts
        return self._ident_counts

    def string_literals(self) -> set[str]:
        if self._string_literals is None:
            values: set[str] = set()
            for rel in self.java_paths():
                for m in _STRING_LIT_RE.finditer(self.noc_text(rel)):
                    values.add(m.group(1))
            self._string_literals = values
        return self._string_literals

    def class_decls(self) -> list[_ClassDecl]:
        if self._class_decls is None:
            decls: list[_ClassDecl] = []
            pattern = re.compile(
                r"\b(?:class|record)\s+([A-Za-z_$][\w$]*)([^{;]*?)\bimplements\b([^{;]*)\{",
                re.S,
            )
            for rel in self.java_paths():
                text = self.noc_text(rel)
                for m in pattern.finditer(text):
                    impls = [
                        re.match(r"\s*([A-Za-z_$][\w$.]*)", part).group(1).split(".")[-1]
                        for part in m.group(3).split(",")
                        if re.match(r"\s*([A-Za-z_$][\w$.]*)", part)
                    ]
                    decls.append(
                        _ClassDecl(
                            path=rel,
                            name=m.group(1),
                            kind="class",
                            implements=impls,
                            line=text[: m.start()].count("\n") + 1,
                        )
                    )
            decls.sort(key=lambda d: (d.path, d.line, d.name))
            self._class_decls = decls
        return self._class_decls

    def tokens_for(self, rel: str) -> tuple[list[str], list[int]]:
        cached = self._tokens.get(rel)
        if cached is not None:
            return cached
        if self._token_budget <= 0:
            empty: tuple[list[str], list[int]] = ([], [])
            self._tokens[rel] = empty
            return empty
        tokens, lines = _tokenize(self.noc_text(rel))
        if len(tokens) > 200_000:
            tokens, lines = [], []
        else:
            self._token_budget -= len(tokens)
        self._tokens[rel] = (tokens, lines)
        return self._tokens[rel]

    def sql_corpus(self) -> list[tuple[str, int, str]]:
        """(path, line, normalized_sql) for every SQL statement found."""
        out: list[tuple[str, int, str]] = []
        for rel in self.java_paths():
            text = self.noc_text(rel)
            for m in _STRING_LIT_RE.finditer(text):
                raw = m.group(1)
                norm = _normalize_sql(raw)
                if norm:
                    out.append((rel, text[: m.start()].count("\n") + 1, norm))
        for rel in self.side_paths():
            if not rel.lower().endswith(".xml"):
                continue
            text = self.side_text(rel)
            for m in _XML_STMT_RE.finditer(text):
                norm = _normalize_sql(m.group(3))
                if norm:
                    out.append((rel, text[: m.start()].count("\n") + 1, norm))
        out.sort(key=lambda x: (x[0], x[1]))
        return out

    def changelog_text(self) -> str:
        if self._changelog is not None:
            return self._changelog
        text = ""
        for rel in self.side_paths():
            base = Path(rel).name.lower()
            if base.startswith(("changelog", "release-notes", "history")):
                text = self.side_text(rel)
                break
        if not text:
            for candidate in (
                self.root / "CHANGELOG.md",
                self.root / "CHANGELOG",
                self.root / "CHANGELOG.rst",
                self.root / "CHANGES.md",
            ):
                if candidate.is_file():
                    text = read_text(candidate, max_bytes=MAX_FILE_BYTES)
                    break
        self._changelog = text
        return text

    def config_text(self) -> str:
        parts: list[str] = []
        for rel in self.side_paths():
            if rel.lower().endswith((".properties", ".yml", ".yaml")):
                parts.append(self.side_text(rel))
        return "\n".join(parts)


def _normalize_sql(raw: str) -> str:
    text = raw.strip()
    if not _SQL_STMT_RE.match(text):
        return ""
    text = text.lower()
    text = re.sub(r"#\{[^}]*\}|\$\{[^}]*\}", "?", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().rstrip(";").strip()


# --------------------------------------------------------------------------
# analyzer
# --------------------------------------------------------------------------


class JavaNativeAnalyzer(EvidenceProvider):
    """Deterministic, low-false-positive Java analyzer."""

    name = PROVIDER_NAME
    kind = EvidenceKind.DETERMINISTIC
    categories = (
        Category.DEAD_CODE,
        Category.DUPLICATION,
        Category.WRONG_ABSTRACTION,
        Category.OVER_ENGINEERING,
        Category.COMPLEXITY,
        Category.LARGE_METHOD,
        Category.LARGE_CLASS,
        Category.COMPATIBILITY_JUNK,
        Category.ERROR_HANDLING,
        Category.CONCURRENCY,
        Category.RESOURCE_SAFETY,
        Category.DATABASE,
        Category.PERFORMANCE,
        Category.TESTABILITY,
        Category.CONFIG_INFLATION,
    )

    # ------------------------------------------------------------ contract

    def version(self) -> Optional[str]:
        return "native-java/1"

    def available(self) -> tuple[bool, Optional[str]]:
        return True, None

    def supports(self, ctx: ScanContext) -> bool:
        for cf in ctx.changed_files:
            if cf.is_binary or cf.change_kind is ChangeKind.DELETED:
                continue
            if cf.language is Language.JAVA or cf.path.lower().endswith(".java"):
                return True
        return False

    def scan(self, ctx: ScanContext) -> ProviderResult:
        timer = self.timer()
        with timer:
            try:
                findings = self._scan(ctx)
            except Exception as exc:  # noqa: BLE001 - providers must never raise
                err = ToolError(
                    provider=self.name,
                    kind=ToolFailureKind.CRASHED,
                    detail=f"{type(exc).__name__}: {exc}",
                    evidence_gap=False,
                )
                return ProviderResult(
                    provider=self.name,
                    status=ToolStatus.DEGRADED,
                    error=err,
                    duration_ms=timer.duration_ms,
                    version=self.version(),
                )
        return ProviderResult(
            provider=self.name,
            status=ToolStatus.OK,
            findings=findings,
            duration_ms=timer.duration_ms,
            version=self.version(),
        )

    # ---------------------------------------------------------------- scan

    def _thresholds(self, ctx: ScanContext) -> dict[str, int]:
        configured = getattr(ctx.config, "complexity_thresholds", None) or {}
        merged = dict(DEFAULT_COMPLEXITY)
        for key, value in configured.items():
            if key in merged:
                merged[key] = int(value)
        return merged

    def _dup_min_tokens(self, ctx: ScanContext) -> int:
        value = getattr(ctx.config, "duplication_min_tokens", None)
        if isinstance(value, int) and value > 0:
            return value
        return DEFAULT_DUP_MIN_TOKENS

    def _scan(self, ctx: ScanContext) -> list[RawFinding]:
        whole = bool(ctx.options.get("whole_file"))
        changed = [
            cf
            for cf in ctx.changed_files
            if not cf.is_binary
            and cf.change_kind is not ChangeKind.DELETED
            and (cf.language is Language.JAVA or cf.path.lower().endswith(".java"))
        ]
        changed_xml = [
            cf
            for cf in ctx.changed_files
            if not cf.is_binary
            and cf.change_kind is not ChangeKind.DELETED
            and cf.path.lower().endswith(".xml")
        ]
        if not changed:
            return []

        index = _RepoIndex(ctx)
        thresholds = self._thresholds(ctx)
        dup_min = self._dup_min_tokens(ctx)

        models: dict[str, _JavaFile] = {}
        for cf in sorted(changed, key=lambda c: c.path):
            text = index.java_text(cf.path)
            if not text:
                text = read_text(ctx.repo_root / cf.path, max_bytes=MAX_FILE_BYTES)
            models[cf.path] = _parse_java(cf.path, text)

        out: list[RawFinding] = []
        for path in sorted(models):
            m = models[path]
            self._rule_unused_private_method(ctx, index, m, out, whole)
            self._rule_unused_field(ctx, index, m, out, whole)
            self._rule_unreachable_branch(ctx, m, out, whole)
            self._rule_commented_code(ctx, m, out, whole)
            self._rule_todo_marker(ctx, m, out, whole)
            self._rule_debug_residue(ctx, m, out, whole)
            self._rule_single_impl_interface(ctx, index, m, out, whole)
            self._rule_single_call_wrapper(ctx, index, m, out, whole)
            self._rule_speculative_factory(ctx, index, m, out, whole)
            self._rule_unused_config_key(ctx, index, m, out, whole)
            self._rule_compat_junk(ctx, index, m, out, whole)
            self._rule_large_method(ctx, m, out, whole, thresholds)
            self._rule_deep_nesting(ctx, m, out, whole, thresholds)
            self._rule_cyclomatic(ctx, m, out, whole, thresholds)
            self._rule_large_class(ctx, m, out, whole, thresholds)
            self._rule_long_param_list(ctx, m, out, whole)
            self._rule_empty_catch(ctx, m, out, whole)
            self._rule_catch_return_null(ctx, m, out, whole)
            self._rule_swallow_and_success(ctx, m, out, whole)
            self._rule_generic_catch(ctx, m, out, whole)
            self._rule_retry_amplify(ctx, m, out, whole)
            self._rule_unclosed_resource(ctx, m, out, whole)
            self._rule_executor_per_call(ctx, m, out, whole)
            self._rule_threadpool_no_shutdown(ctx, index, m, out, whole)
            self._rule_shared_mutable(ctx, m, out, whole)
            self._rule_semaphore_leak(ctx, m, out, whole)
            self._rule_lock_remote_call(ctx, m, out, whole)
            self._rule_double_check_no_volatile(ctx, m, out, whole)
            self._rule_no_idempotency(ctx, m, out, whole)
            self._rule_nplus1(ctx, m, out, whole)
            self._rule_update_no_where(ctx, index, m, out, whole)
            self._rule_delete_no_where(ctx, index, m, out, whole)
            self._rule_tx_remote_call(ctx, m, out, whole)
            self._rule_select_star(ctx, index, m, out, whole)
            self._rule_unbounded_in(ctx, index, m, out, whole)
            self._rule_on2(ctx, m, out, whole)
            self._rule_repeat_serialize(ctx, m, out, whole)
            self._rule_hardcoded_time(ctx, m, out, whole)
            self._rule_global_mutable_singleton(ctx, m, out, whole)

        self._rule_duplicate_block(ctx, index, models, out, whole, dup_min)
        self._rule_duplicate_business_rule(ctx, index, models, out, whole)
        self._rule_dup_sql(ctx, index, models, out, whole)
        self._rule_update_no_where_xml(ctx, index, changed_xml, out, whole)
        self._rule_delete_no_where_xml(ctx, index, changed_xml, out, whole)

        out.sort(key=lambda r: (r.file, r.start_line, r.rule_id))
        return out

    # ------------------------------------------------------------- helpers

    def _emit(
        self,
        ctx: ScanContext,
        out: list[RawFinding],
        path: str,
        rule_id: str,
        message: str,
        start: int,
        end: int,
        symbol: Optional[str],
        category: Category,
        severity: Severity,
        confidence: float,
        detail: str,
        extra: dict[str, Any],
        whole: bool,
    ) -> None:
        if not whole:
            line = None
            for ln in range(start, end + 1):
                if ctx.is_changed_line(path, ln):
                    line = ln
                    break
            if line is None:
                return
        else:
            line = start
        out.append(
            RawFinding(
                provider=self.name,
                rule_id=rule_id,
                message=message,
                file=path,
                start_line=line,
                end_line=max(line, end),
                symbol=symbol,
                category=category,
                severity=severity,
                confidence=confidence,
                kind=EvidenceKind.DETERMINISTIC,
                detail=detail,
                extra=extra,
            )
        )

    @staticmethod
    def _snippet(m: _JavaFile, line: int) -> str:
        if 1 <= line <= len(m.raw_lines):
            return m.raw_lines[line - 1].strip()[:300]
        return ""

    @staticmethod
    def _has_annotation(annotations: Iterable[tuple[int, str]], names: Iterable[str]) -> bool:
        wanted = set(names)
        for name in _annotation_names(annotations):
            if name in wanted:
                return True
        return False

    # ------------------------------------------------------- dead / stale

    def _rule_unused_private_method(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        counts = index.ident_counts()
        literals = index.string_literals()
        emitted = 0
        suppressed_annotations = {
            "Scheduled",
            "EventListener",
            "PostConstruct",
            "Bean",
            "KafkaListener",
            "RabbitListener",
            "JmsListener",
            "XxlJob",
            "Async",
            "Cacheable",
            "PreDestroy",
            "Override",
        }
        for method in m.methods:
            if emitted >= MAX_FINDINGS_PER_RULE_PER_FILE:
                break
            if method.is_ctor or "private" not in method.mods.split():
                continue
            if method.is_abstract:
                continue
            owner = m.class_at(method.open_line)
            if owner is not None and owner.kind == "interface":
                # `private` members cannot exist in an interface contract
                continue
            if self._has_annotation(method.annotations, suppressed_annotations):
                continue
            if owner is not None and owner.name in literals:
                # class name used as a reflective/SPI string -> dynamic entry
                continue
            if method.name in literals:
                continue
            if counts.get(method.name, 0) > 1:
                continue
            line = method.decl_line + 1
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD",
                f"Private method '{method.name}' is never referenced",
                line,
                line,
                method.name,
                Category.DEAD_CODE,
                Severity.MEDIUM,
                0.85,
                "zero references in the whole repository after removing the definition",
                {
                    "matched_snippet": self._snippet(m, line),
                    "line": line,
                    "reason": "identifier appears exactly once (the declaration)",
                    "occurrences": counts.get(method.name, 0),
                },
                whole,
            )
            emitted += 1

    def _rule_unused_field(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        counts = index.ident_counts()
        literals = index.string_literals()
        emitted = 0
        suppress = {
            "Autowired",
            "Resource",
            "Value",
            "Inject",
            "Getter",
            "Setter",
            "Data",
            "JsonProperty",
            "JsonIgnore",
            "ConfigurationProperties",
            "PersistenceContext",
            "Qualifier",
        }
        for fld in m.fields:
            if emitted >= MAX_FINDINGS_PER_RULE_PER_FILE:
                break
            mods = fld.mods.split()
            if "private" not in mods:
                continue
            if "static" in mods and "final" in mods:
                continue
            if self._has_annotation(fld.annotations, suppress):
                continue
            owner = m.class_at(fld.line)
            if owner is not None and self._has_annotation(owner.annotations, suppress):
                # Lombok / DI annotations on the enclosing type also imply access
                continue
            if fld.name in literals:
                continue
            if counts.get(fld.name, 0) > 1:
                continue
            line = fld.line + 1
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-UNUSED-FIELD",
                f"Private field '{fld.name}' is never referenced",
                line,
                line,
                fld.name,
                Category.DEAD_CODE,
                Severity.LOW,
                0.8,
                "zero references in the whole repository after removing the declaration",
                {
                    "matched_snippet": self._snippet(m, line),
                    "line": line,
                    "reason": "identifier appears exactly once (the declaration)",
                    "occurrences": counts.get(fld.name, 0),
                },
                whole,
            )
            emitted += 1

    def _rule_unreachable_branch(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for i, line in enumerate(m.skel_lines):
            if not _UNREACHABLE_RE.search(line):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-UNREACHABLE-BRANCH",
                "Branch on a constant boolean literal is unreachable code",
                i + 1,
                i + 1,
                None,
                Category.DEAD_CODE,
                Severity.LOW,
                0.9,
                "if/while guarded by a literal true/false",
                {
                    "matched_snippet": self._snippet(m, i + 1),
                    "line": i + 1,
                    "reason": "constant literal condition",
                },
                whole,
            )

    def _rule_commented_code(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        runs: list[tuple[int, int, list[str]]] = []
        current: list[str] = []
        start_line = 0
        in_block = False
        for i, raw in enumerate(m.raw_lines):
            stripped = raw.strip()
            is_comment = False
            if in_block:
                is_comment = True
                if "*/" in stripped:
                    in_block = False
            elif stripped.startswith("//"):
                is_comment = True
            elif stripped.startswith("/*"):
                is_comment = True
                if "*/" not in stripped:
                    in_block = True
            if is_comment:
                if not current:
                    start_line = i + 1
                current.append(stripped)
            else:
                if len(current) >= 5:
                    runs.append((start_line, i, list(current)))
                current = []
        if len(current) >= 5:
            runs.append((start_line, len(m.raw_lines), list(current)))

        for begin, end, chunk in runs:
            content = []
            for item in chunk:
                text = item
                for marker in ("//", "/*", "*/"):
                    text = text.replace(marker, " ")
                text = text.lstrip("*").strip()
                if text:
                    content.append(text)
            joined = " ".join(content)
            if ";" not in joined:
                continue
            markers = sum(1 for ch in ("=", "(", "{") if ch in joined)
            if markers < 2:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-COMMENTED-CODE",
                "Large block of commented-out code",
                begin,
                end,
                None,
                Category.DEAD_CODE,
                Severity.LOW,
                0.7,
                f"{len(chunk)} consecutive comment lines that look like code",
                {
                    "matched_snippet": chunk[0][:200],
                    "line": begin,
                    "reason": "comment run >= 5 lines containing ';' and code punctuation",
                    "run_length": len(chunk),
                },
                whole,
            )

    def _rule_todo_marker(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for i, raw in enumerate(m.raw_lines):
            match = _TODO_RE.search(raw)
            if match is None:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-TODO-MARKER",
                f"{match.group(1)} marker left in code",
                i + 1,
                i + 1,
                None,
                Category.DEAD_CODE,
                Severity.LOW,
                0.9,
                "TODO/FIXME/XXX/HACK marker in a comment",
                {
                    "matched_snippet": raw.strip()[:200],
                    "line": i + 1,
                    "reason": "unresolved marker",
                },
                whole,
            )

    def _rule_debug_residue(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        if TEST_PATH_RE.search(m.path):
            return
        for i, line in enumerate(m.skel_lines):
            if not _DEBUG_RE.search(line):
                continue
            enclosing = m.method_at(i)
            if enclosing is not None and enclosing.name == "main":
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-DEBUG-RESIDUE",
                "Debug print statement left in production code",
                i + 1,
                i + 1,
                enclosing.name if enclosing else None,
                Category.DEAD_CODE,
                Severity.LOW,
                0.9,
                "System.out/System.err/printStackTrace in a non-test path",
                {
                    "matched_snippet": self._snippet(m, i + 1),
                    "line": i + 1,
                    "reason": "debug residue",
                },
                whole,
            )

    # ------------------------------------------------------- abstraction

    def _rule_single_impl_interface(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        pkg_match = _PKG_RE.search("\n".join(m.noc_lines[:60]))
        package = pkg_match.group(1) if pkg_match else ""
        impls = index.class_decls()
        idents = index.ident_counts()

        for cls in m.classes:
            if cls.kind != "interface":
                continue
            if self._has_annotation(cls.annotations, ("FeignClient", "Mapper", "DubboService", "RemoteService")):
                continue
            if _SPI_BOUNDARY_RE.search(m.noc_lines[cls.decl_line]):
                continue
            implementations = [d for d in impls if cls.name in d.implements]
            if len(implementations) != 1:
                continue
            # every method must be a pure signature (no default body)
            own = [x for x in m.methods if x.class_name == cls.name and x.decl_line > cls.decl_line]
            if not own:
                continue
            if any(not x.is_abstract for x in own):
                continue
            # injection points: >= 2 means the boundary is genuinely shared
            injected_total = 0
            for rel in index.java_paths():
                text = index.noc_text(rel)
                for match in re.finditer(r"@(?:Autowired|Resource|Inject)\b", text):
                    tail = text[match.end() : match.end() + 200]
                    if re.search(r"\b" + re.escape(cls.name) + r"\b", tail):
                        injected_total += 1
            if injected_total >= 2:
                continue

            severity = Severity.MEDIUM
            confidence = 0.7
            note = ""
            if re.search(r"(?:^|\.)(?:api|spi|client|remote|facade)(?:\.|$)", package):
                severity = Severity.LOW
                confidence = 0.5
                note = "package suggests an SPI/RPC boundary - needs manual confirmation"
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE",
                f"Interface '{cls.name}' has exactly one implementation",
                cls.decl_line + 1,
                cls.decl_line + 1,
                cls.name,
                Category.WRONG_ABSTRACTION,
                severity,
                confidence,
                f"single implementation {implementations[0].name}, "
                f"{len(own)} abstract methods, {injected_total} injection point(s). {note}".strip(),
                {
                    "matched_snippet": self._snippet(m, cls.decl_line + 1),
                    "line": cls.decl_line + 1,
                    "reason": "one implementation, no default methods, no SPI annotation",
                    "implementation": implementations[0].name,
                    "injection_points": injected_total,
                    "needs_manual_confirmation": bool(note),
                },
                whole,
            )

    def _rule_single_call_wrapper(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        idents = index.ident_counts()
        for cls in m.classes:
            if cls.kind != "class":
                continue
            if cls.name in ("Factory", "Builder", "Registry"):
                continue
            public_methods = [
                x
                for x in m.methods
                if x.class_name == cls.name
                and not x.is_ctor
                and not x.is_abstract
                and "public" in x.mods.split()
            ]
            if len(public_methods) < 2:
                continue
            body_text = "\n".join(m.skel_lines[cls.open_line + 1 : cls.close_line])
            if re.search(r"\bcatch\b|\bthrow\b|\blog(?:ger)?\s*\.|@Transactional|@Retryable|@CircuitBreaker", body_text):
                continue
            delegates: list[str] = []
            for method in public_methods:
                body = method.body_text(m.skel_lines).strip()
                body = " ".join(body.split())
                pattern = re.compile(
                    r"^(?:return\s+)?[A-Za-z_$][\w$]*\s*\.\s*"
                    + re.escape(method.name)
                    + r"\s*\([^;]*\)\s*;?$"
                )
                if not pattern.match(body):
                    delegates = []
                    break
                delegates.append(method.name)
            if not delegates:
                continue
            # third-party SDK isolation -> legitimate boundary (ABS-003)
            own_pkg = ""
            pkg_match = _PKG_RE.search("\n".join(m.noc_lines[:60]))
            if pkg_match:
                own_pkg = pkg_match.group(1)
            own_root = own_pkg.split(".")[0] if own_pkg else ""
            third_party = False
            for line in m.noc_lines[:120]:
                stripped = line.strip()
                if not stripped.startswith("import ") or stripped.startswith("import static"):
                    continue
                imported = stripped[len("import ") :].rstrip(";").strip()
                if imported.startswith(("java.", "javax.", "jakarta.")):
                    continue
                imported_pkg = imported.rsplit(".", 1)[0] if "." in imported else imported
                if own_root and imported_pkg.split(".")[0] == own_root:
                    continue
                third_party = True
                break
            if third_party:
                continue
            if idents.get(cls.name, 0) > 2:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-SINGLE-CALL-WRAPPER",
                f"Class '{cls.name}' only forwards calls to a single collaborator",
                cls.decl_line + 1,
                cls.decl_line + 1,
                cls.name,
                Category.WRONG_ABSTRACTION,
                Severity.MEDIUM,
                0.6,
                f"{len(delegates)} methods all delegate verbatim; single caller",
                {
                    "matched_snippet": self._snippet(m, cls.decl_line + 1),
                    "line": cls.decl_line + 1,
                    "reason": "pure delegation, no validation/logging/error translation",
                    "delegated_methods": sorted(delegates),
                    "own_package": own_pkg,
                },
                whole,
            )

    def _rule_speculative_factory(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        suffixes = ("Factory", "Provider", "Registry", "Builder")
        declared = [c for c in m.classes if c.name.endswith(suffixes)]
        if len(declared) < 2:
            return
        names = sorted(c.name for c in declared)
        implementations = [
            d for d in index.class_decls() if any(n in d.implements for n in names)
        ]
        registrations = 0
        for rel in index.java_paths():
            text = index.noc_text(rel)
            for name in names:
                registrations += len(re.findall(r"\bregister\s*\(\s*" + re.escape(name), text))
                registrations += len(re.findall(r"\bnew\s+" + re.escape(name) + r"\s*\(", text))
        if len(implementations) >= 2 or registrations >= 2:
            return
        first = declared[0]
        self._emit(
            ctx,
            out,
            m.path,
            "CHM-JAVA-NAT-SPECULATIVE-FACTORY",
            "Factory/Provider/Registry/Builder cluster with a single implementation",
            first.decl_line + 1,
            first.decl_line + 1,
            first.name,
            Category.OVER_ENGINEERING,
            Severity.MEDIUM,
            0.65,
            f"{len(declared)} abstraction types ({', '.join(names)}) with "
            f"{len(implementations)} implementation(s) and {registrations} registration(s)",
            {
                "matched_snippet": self._snippet(m, first.decl_line + 1),
                "line": first.decl_line + 1,
                "reason": "abstraction count exceeds implementation count",
                "types": names,
                "implementations": len(implementations),
                "registrations": registrations,
            },
            whole,
        )

    def _rule_unused_config_key(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        config_text = index.config_text()
        if not config_text:
            return
        for i, raw in enumerate(m.noc_lines):
            for match in _VALUE_RE.finditer(raw):
                key = match.group(1).strip()
                default = match.group(2)
                if default is not None:
                    continue
                if key in config_text:
                    continue
                if re.search(r"(?:^|\n)\s*" + re.escape(key) + r"\s*[:=]", config_text):
                    continue
                self._emit(
                    ctx,
                    out,
                    m.path,
                    "CHM-JAVA-NAT-UNUSED-CONFIG-KEY",
                    f"Config key '{key}' is not present in any properties/yaml file",
                    i + 1,
                    i + 1,
                    key,
                    Category.CONFIG_INFLATION,
                    Severity.LOW,
                    0.7,
                    "no matching key in .properties/.yml/.yaml, no default value",
                    {
                        "matched_snippet": raw.strip()[:200],
                        "line": i + 1,
                        "reason": "referenced key absent from configuration files",
                        "key": key,
                    },
                    whole,
                )

    def _rule_compat_junk(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        changelog = index.changelog_text().lower()
        candidates: list[tuple[int, str, str]] = []
        for cls in m.classes:
            candidates.append((cls.decl_line, cls.name, "class"))
        for method in m.methods:
            candidates.append((method.decl_line, method.name, "method"))
        for fld in m.fields:
            candidates.append((fld.line, fld.name, "field"))

        for line0, name, kind in candidates:
            words = _camel_words(name)
            hits = [w for w in words if w in _COMPAT_WORDS]
            if not hits:
                continue
            if kind == "class":
                annotations = next((c.annotations for c in m.classes if c.decl_line == line0), [])
            elif kind == "method":
                annotations = next((x.annotations for x in m.methods if x.decl_line == line0), [])
            else:
                annotations = next((x.annotations for x in m.fields if x.line == line0), [])
            if self._has_annotation(annotations, ("Deprecated",)):
                continue
            if changelog and name.lower() in changelog:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-COMPAT-JUNK",
                f"{kind.title()} '{name}' looks like compatibility junk",
                line0 + 1,
                line0 + 1,
                name,
                Category.COMPATIBILITY_JUNK,
                Severity.LOW,
                0.6,
                f"name contains {sorted(set(hits))}, no @Deprecated, no CHANGELOG evidence. "
                "需人工确认，禁止自动删除。",
                {
                    "matched_snippet": self._snippet(m, line0 + 1),
                    "line": line0 + 1,
                    "reason": "compat-looking identifier without an explicit deprecation contract",
                    "matched_words": sorted(set(hits)),
                    "recommendation": "需人工确认，禁止自动删除",
                },
                whole,
            )

    # -------------------------------------------------------- complexity

    def _rule_large_method(
        self,
        ctx: ScanContext,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
        thresholds: dict[str, int],
    ) -> None:
        limit = thresholds["method_lines"]
        emitted = 0
        for method in m.methods:
            if emitted >= MAX_FINDINGS_PER_RULE_PER_FILE:
                break
            if method.is_ctor or method.is_abstract:
                continue
            lines = method.body_line_count()
            if lines <= limit:
                continue
            body = method.body_text(m.skel_lines)
            cyclo = _cyclomatic(body)
            if cyclo > 8:
                severity = Severity.MEDIUM
                confidence = 0.75
                reason = f"{lines} lines and cyclomatic complexity {cyclo}"
            else:
                # CPLX-003 counter-example: a long pure mapping method stays LOW
                severity = Severity.LOW
                confidence = 0.55
                reason = f"{lines} lines but low complexity ({cyclo}) - likely pure mapping"
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-LARGE-METHOD",
                f"Method '{method.name}' is {lines} lines long",
                method.decl_line + 1,
                method.close_line + 1,
                method.name,
                Category.LARGE_METHOD,
                severity,
                confidence,
                reason,
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": reason,
                    "body_lines": lines,
                    "cyclomatic": cyclo,
                },
                whole,
            )
            emitted += 1

    def _rule_deep_nesting(
        self,
        ctx: ScanContext,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
        thresholds: dict[str, int],
    ) -> None:
        limit = thresholds["nesting_depth"]
        for method in m.methods:
            if method.is_ctor or method.is_abstract:
                continue
            body = method.body_text(m.skel_lines)
            if not body:
                continue
            depth = _max_control_nesting(body)
            if depth <= limit:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-DEEP-NESTING",
                f"Method '{method.name}' nests control flow {depth} levels deep",
                method.decl_line + 1,
                method.close_line + 1,
                method.name,
                Category.COMPLEXITY,
                Severity.MEDIUM,
                0.8,
                f"maximum control-flow nesting {depth} > {limit}",
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": f"nesting depth {depth} exceeds {limit}",
                    "depth": depth,
                },
                whole,
            )

    def _rule_cyclomatic(
        self,
        ctx: ScanContext,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
        thresholds: dict[str, int],
    ) -> None:
        limit = thresholds["method_cyclomatic"]
        for method in m.methods:
            if method.is_ctor or method.is_abstract:
                continue
            body = method.body_text(m.skel_lines)
            if not body:
                continue
            cyclo = _cyclomatic(body)
            if cyclo <= limit:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-CYCLOMATIC",
                f"Method '{method.name}' has cyclomatic complexity {cyclo}",
                method.decl_line + 1,
                method.close_line + 1,
                method.name,
                Category.COMPLEXITY,
                Severity.MEDIUM,
                0.8,
                f"cyclomatic complexity {cyclo} > {limit}",
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": f"cyclomatic complexity {cyclo} exceeds {limit}",
                    "cyclomatic": cyclo,
                },
                whole,
            )

    def _rule_large_class(
        self,
        ctx: ScanContext,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
        thresholds: dict[str, int],
    ) -> None:
        limit = thresholds["class_lines"]
        for cls in m.classes:
            lines = cls.close_line - cls.decl_line
            methods = len([x for x in m.methods if x.class_name == cls.name and not x.is_ctor])
            fields = len([x for x in m.fields if x.class_name == cls.name])
            reasons = []
            if lines > limit:
                reasons.append(f"{lines} lines > {limit}")
            if methods > 30:
                reasons.append(f"{methods} methods > 30")
            if fields > 30:
                reasons.append(f"{fields} fields > 30")
            if not reasons:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-LARGE-CLASS",
                f"Class '{cls.name}' is oversized",
                cls.decl_line + 1,
                cls.decl_line + 1,
                cls.name,
                Category.LARGE_CLASS,
                Severity.LOW,
                0.7,
                "; ".join(reasons),
                {
                    "matched_snippet": self._snippet(m, cls.decl_line + 1),
                    "line": cls.decl_line + 1,
                    "reason": "; ".join(reasons),
                    "lines": lines,
                    "methods": methods,
                    "fields": fields,
                },
                whole,
            )

    def _rule_long_param_list(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for method in m.methods:
            if len(method.params) <= 5:
                continue
            if method.is_ctor:
                continue
            owner = m.class_at(method.open_line)
            if owner is not None and self._has_annotation(owner.annotations, ("Builder",)):
                continue
            if method.name.endswith("Mapper") or (owner is not None and owner.name.endswith("Mapper")):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-LONG-PARAM-LIST",
                f"Method '{method.name}' takes {len(method.params)} parameters",
                method.decl_line + 1,
                method.decl_line + 1,
                method.name,
                Category.COMPLEXITY,
                Severity.LOW,
                0.8,
                f"{len(method.params)} parameters > 5",
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": "long parameter list",
                    "param_count": len(method.params),
                },
                whole,
            )

    # ---------------------------------------------------- error handling

    def _keyword_blocks(
        self, m: _JavaFile, keyword_re: "re.Pattern[str]", text: Optional[str] = None
    ) -> list[tuple[int, int, int, str, str, int, int, int]]:
        """Locate ``keyword (...) { ... }`` blocks by character offset.

        Returns 0-based ``(head_line, open_line, close_line, header, body,
        open_offset, close_offset, keyword_offset)`` where ``body`` is the
        exact skeleton text between the braces.  Using offsets (instead of
        line shapes) keeps single-line constructs such as
        ``try { a(); } catch (E e) { }`` visible.

        ``text`` defaults to ``m.skel_text``; pass an offset-preserving
        skeleton (``_aligned_skeleton(m.raw_text)``) when the returned offsets
        will be used to index ``m.raw_text``.
        """
        if text is None:
            text = m.skel_text
            line_starts = m.line_starts
        else:
            line_starts = _line_starts(text)
        out: list[tuple[int, int, int, str, str, int, int, int]] = []
        for match in keyword_re.finditer(text):
            cursor = match.end() - 1
            if text[cursor] == "(":
                close_paren = _paren_match(text, cursor)
                if close_paren < 0:
                    continue
                header = text[match.start() : close_paren + 1]
                cursor = close_paren + 1
                while cursor < len(text) and text[cursor] in " \t\r\n":
                    cursor += 1
                if cursor >= len(text) or text[cursor] != "{":
                    continue
            elif text[cursor] == "{":
                header = text[match.start() : match.end()]
            else:
                continue
            close_brace = _brace_match(text, cursor)
            if close_brace < 0:
                continue
            out.append(
                (
                    bisect.bisect_right(line_starts, match.start()) - 1,
                    bisect.bisect_right(line_starts, cursor) - 1,
                    bisect.bisect_right(line_starts, close_brace) - 1,
                    " ".join(header.split()),
                    text[cursor + 1 : close_brace],
                    cursor,
                    close_brace,
                    match.start(),
                )
            )
        return out

    def _catch_blocks(self, m: _JavaFile) -> list[tuple[int, int, int, str, str]]:
        return [b[:5] for b in self._keyword_blocks(m, _CATCH_ANY_RE)]

    def _catch_spans(
        self, m: _JavaFile, text: Optional[str] = None
    ) -> list["_CatchSpan"]:
        """``_keyword_blocks`` for ``catch`` with the parameter unwrapped."""
        out: list[_CatchSpan] = []
        for block in self._keyword_blocks(m, _CATCH_ANY_RE, text):
            head, open_line, close_line, header, body, ob, cb, kw = block
            inner = header[len("catch") :].strip()
            if inner.startswith("(") and inner.endswith(")"):
                inner = inner[1:-1]
            out.append(
                _CatchSpan(
                    head_line=head,
                    open_line=open_line,
                    close_line=close_line,
                    param=" ".join(inner.split()),
                    body=body,
                    open_offset=ob,
                    close_offset=cb,
                    keyword_offset=kw,
                )
            )
        return out

    def _loop_blocks(self, m: _JavaFile) -> list[tuple[int, int, int, str, str]]:
        return [b[:5] for b in self._keyword_blocks(m, _LOOP_ANY_RE)]

    def _rule_empty_catch(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        # ``m.skel_text`` drops the comment delimiters, so its offsets do not
        # index ``m.raw_text``; this rule needs the real body text.
        skel = _aligned_skeleton(m.raw_text)
        for span in self._catch_spans(m, skel):
            head = span.head_line
            exc = span.param
            if span.body.strip():
                continue
            raw_body = m.raw_text[span.open_offset + 1 : span.close_offset]
            if not _comment_only(raw_body):
                # the skeleton blanked a statement (e.g. a bare string literal)
                continue
            if re.search(r"(?:throw|log(?:ger)?\s*\.|counter|meter|metrics|metric)\b", raw_body):
                continue
            benign = re.search(
                r"(?:ignore|noop|no-op|intentionally|expected|swallow)", raw_body, re.I
            )

            # Java catch parameter: ``Exception e`` / ``A | B e`` -> last word.
            words = _IDENT_RE.findall(exc)
            binding = words[-1] if words else ""
            unused_binding = bool(_JAVA_UNUSED_BINDING_RE.match(binding))
            try_pair = _enclosing_try(skel, span.keyword_offset)
            probe = bool(
                _JAVA_PROBE_CALL_RE.search(skel[try_pair[0] + 1 : try_pair[1]])
                if try_pair is not None
                else False
            )
            has_comment = bool(re.search(r"//|/\*", raw_body))

            signals: list[str] = []
            if benign:
                signals.append("catch body carries an explicit ignore comment")
            if unused_binding:
                signals.append("catch parameter is deliberately unused")
            if probe:
                signals.append("try body only probes / parses / cleans up")
            if has_comment:
                signals.append("catch block carries a comment")

            # Downgrade (never suppress) when the shape says "intentional":
            #   * the author annotated the catch (comment / ignore wording), or
            #   * the try body is a probe/parse/cleanup, or
            #   * the parameter is named ``ignored``/``_``/``unused`` -- in Java
            #     the variable name *is* the only idiomatic "unused" annotation,
            #     so unlike the JS side it downgrades on its own.
            # ``catch (Exception e) {}`` with none of these stays HIGH
            # (spec CHM-ERR-001).
            downgrade = bool(benign) or has_comment or probe or unused_binding
            detail = (
                "empty catch body; "
                + "; ".join(signals)
                + " - 疑似合理降级，需语义确认"
                if downgrade
                else "catch block contains no statements at all"
            )
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-EMPTY-CATCH",
                f"Empty catch block for {exc or 'exception'}",
                head + 1,
                head + 1,
                exc or None,
                Category.ERROR_HANDLING,
                Severity.LOW if downgrade else Severity.HIGH,
                0.5 if downgrade else 0.9,
                detail,
                {
                    "matched_snippet": self._snippet(m, head + 1),
                    "line": head + 1,
                    "reason": detail,
                    "exception": exc,
                    "signals": signals,
                    "note": (
                        "looks like an intentional probe/cleanup; confirm"
                        if downgrade
                        else ""
                    ),
                },
                whole,
            )

    def _rule_catch_return_null(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for head, open_line, close_line, exc, body in self._catch_blocks(m):
            flattened = " ".join(body.split())
            if not re.fullmatch(r"return\s+null\s*;?", flattened):
                continue
            method = m.method_at(open_line)
            if method is None:
                continue
            if method.ret.strip().startswith("Optional"):
                continue
            if re.search(r"(?:OrNull|Safe|Try|Optional)$", method.name):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-CATCH-RETURN-NULL",
                f"Catch block returns null from '{method.name}'",
                head + 1,
                head + 1,
                method.name,
                Category.ERROR_HANDLING,
                Severity.HIGH,
                0.85,
                "catch block collapses every failure into a null return",
                {
                    "matched_snippet": self._snippet(m, head + 1),
                    "line": head + 1,
                    "reason": "return null inside catch, return type is not Optional",
                    "return_type": method.ret,
                    "exception": exc,
                },
                whole,
            )

    def _rule_swallow_and_success(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for head, open_line, close_line, exc, body in self._catch_blocks(m):
            flattened = " ".join(body.split())
            if not flattened:
                continue
            if re.search(r"\bthrow\b", flattened):
                continue
            if not re.fullmatch(
                r"(?:log(?:ger)?\s*\.\s*(?:warn|info|error|debug)\s*\([^;]*\)\s*;?\s*)+",
                flattened,
            ):
                continue
            method = m.method_at(open_line)
            if method is None:
                continue
            tail = " ".join(method.body_text(m.skel_lines).split())
            if not re.search(
                r"return\s+(?:true|0|1|\"OK\"|\"ok\")\s*;|return\s+Response\s*\.\s*success\s*\(",
                tail,
            ):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-SWALLOW-AND-SUCCESS",
                f"'{method.name}' logs the failure and still reports success",
                head + 1,
                head + 1,
                method.name,
                Category.ERROR_HANDLING,
                Severity.HIGH,
                0.85,
                "catch only logs, method still returns a success value",
                {
                    "matched_snippet": self._snippet(m, head + 1),
                    "line": head + 1,
                    "reason": "swallowed exception with a success return",
                    "exception": exc,
                },
                whole,
            )

    def _rule_generic_catch(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for head, open_line, close_line, exc, body in self._catch_blocks(m):
            if not re.match(r"^(?:Exception|Throwable|RuntimeException)\b", exc):
                continue
            flattened = " ".join(body.split())
            if re.search(r"\bthrow\b", flattened):
                continue
            owner = m.class_at(open_line)
            if owner is not None and re.search(
                r"(?:Controller|Advice|Filter|Interceptor|Job)$", owner.name
            ):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-GENERIC-CATCH",
                f"Broad catch of '{exc}' without rethrow",
                head + 1,
                head + 1,
                exc,
                Category.ERROR_HANDLING,
                Severity.LOW,
                0.75,
                "catch(Exception/Throwable) that neither rethrows nor is a global boundary",
                {
                    "matched_snippet": self._snippet(m, head + 1),
                    "line": head + 1,
                    "reason": "over-broad catch without rethrow",
                    "exception": exc,
                },
                whole,
            )

    def _rule_retry_amplify(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for i, line in enumerate(m.noc_lines):
            if not _RETRY_RE.search(line):
                continue
            window = "\n".join(m.noc_lines[max(0, i - 3) : i + 6])
            if _RETRY_BOUND_RE.search(window):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-RETRY-AMPLIFY",
                "Retry without an attempt bound or backoff",
                i + 1,
                i + 1,
                None,
                Category.ERROR_HANDLING,
                Severity.HIGH,
                0.8,
                "retry annotation with no maxAttempts/maxRetries/backoff",
                {
                    "matched_snippet": line.strip()[:200],
                    "line": i + 1,
                    "reason": "unbounded retry amplification",
                },
                whole,
            )

        for head, open_line, close_line, header, body in self._loop_blocks(m):
            if "catch" not in body or "continue" not in body:
                continue
            window = "\n".join(m.noc_lines[open_line : close_line + 1])
            if _RETRY_BOUND_RE.search(window) or re.search(
                r"\battempts?\b\s*[<>=]|\bcount\b\s*\+\+|\bretries?\b\s*\+\+", window
            ):
                continue
            if not re.search(r"for\s*\(\s*;|while\s*\(\s*true\s*\)|while\s*\(\s*retry", header):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-RETRY-AMPLIFY",
                "Unbounded retry loop",
                head + 1,
                head + 1,
                None,
                Category.ERROR_HANDLING,
                Severity.HIGH,
                0.8,
                "infinite loop with catch+continue and no attempt counter",
                {
                    "matched_snippet": self._snippet(m, head + 1),
                    "line": head + 1,
                    "reason": "retry loop without a bound or backoff",
                },
                whole,
            )

    # -------------------------------------------------------- resource

    def _rule_unclosed_resource(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for i, line in enumerate(m.skel_lines):
            match = _RESOURCE_NEW_RE.search(line)
            if match is None:
                continue
            if re.match(r"^\s*(?:return|throw)\b", line):
                continue
            if re.match(r"^\s*try\s*\(", line) or "try (" in line:
                # try-with-resources header (RES-002 counter-example)
                continue
            method = m.method_at(i)
            if method is None:
                continue
            body = method.body_text(m.skel_lines)
            assign = re.search(
                r"([A-Za-z_$][\w$]*)\s*=\s*new\s+" + re.escape(match.group(1)) + r"\s*\(", line
            )
            var = assign.group(1) if assign else None
            if var is None:
                continue
            if re.search(r"\b" + re.escape(var) + r"\s*\.\s*close\s*\(", body):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-UNCLOSED-RESOURCE",
                f"Resource '{var}' ({match.group(1)}) is never closed",
                i + 1,
                i + 1,
                var,
                Category.RESOURCE_SAFETY,
                Severity.HIGH,
                0.85,
                "resource constructed outside try-with-resources and never closed",
                {
                    "matched_snippet": self._snippet(m, i + 1),
                    "line": i + 1,
                    "reason": "no close() and not a try-with-resources header",
                    "resource_type": match.group(1),
                    "variable": var,
                },
                whole,
            )

    def _rule_executor_per_call(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for i, line in enumerate(m.skel_lines):
            match = _EXECUTOR_RE.search(line)
            if match is None:
                continue
            stripped = line.strip()
            if re.search(r"\bstatic\s+final\b", stripped) or re.search(
                r"\bprivate\s+final\b|\bfinal\s+\w+", stripped
            ):
                continue
            method = m.method_at(i)
            if method is None:
                continue
            if method.is_ctor:
                continue
            if self._has_annotation(method.annotations, ("PostConstruct",)):
                continue
            owner = m.class_at(i)
            if owner is not None and self._has_annotation(
                owner.annotations, ("Component", "Service", "Configuration")
            ):
                target = re.match(r"\s*(?:this\s*\.\s*)?([A-Za-z_$][\w$]*)\s*=", line)
                if target is not None and any(
                    f.name == target.group(1) and f.class_name == owner.name for f in m.fields
                ):
                    continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-EXECUTOR-PER-CALL",
                "Thread pool / thread created on every call",
                i + 1,
                i + 1,
                method.name,
                Category.RESOURCE_SAFETY,
                Severity.HIGH,
                0.85,
                "executor created inside a method body instead of a shared field",
                {
                    "matched_snippet": self._snippet(m, i + 1),
                    "line": i + 1,
                    "reason": "per-call executor allocation",
                },
                whole,
            )

    def _rule_threadpool_no_shutdown(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        pool_creation = re.compile(r"Executors\s*\.\s*new|ThreadPoolTaskExecutor|ThreadPoolExecutor\s*\(")
        for method in m.methods:
            if not self._has_annotation(method.annotations, ("Bean",)):
                continue
            body = method.body_text(m.skel_lines)
            if not pool_creation.search(body):
                continue
            repo_has_shutdown = False
            for rel in index.java_paths():
                if _POOL_SHUTDOWN_RE.search(index.noc_text(rel)):
                    repo_has_shutdown = True
                    break
            if repo_has_shutdown:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-THREADPOOL-NO-SHUTDOWN",
                f"@Bean '{method.name}' creates a thread pool without a visible shutdown",
                method.decl_line + 1,
                method.decl_line + 1,
                method.name,
                Category.RESOURCE_SAFETY,
                Severity.LOW,
                0.55,
                "no shutdown()/@PreDestroy/DisposableBean found in the repository. "
                "生命周期需人工确认，禁止机械判定泄漏",
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": "thread pool lifecycle needs manual confirmation",
                    "recommendation": "生命周期需人工确认，禁止机械判定泄漏",
                },
                whole,
            )

    # ------------------------------------------------------- concurrency

    def _rule_shared_mutable(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for cls in m.classes:
            if not self._has_annotation(
                cls.annotations,
                ("Component", "Service", "Controller", "RestController", "Repository"),
            ):
                continue
            class_text = "\n".join(m.skel_lines[cls.open_line : cls.close_line + 1])
            if _SCOPE_RE.search(class_text):
                continue
            for fld in cls.fields:
                mods = fld.mods.split()
                if "static" in mods:
                    continue
                declaration = fld.type + " " + self._snippet(m, fld.line + 1)
                if not _UNSAFE_COLL_RE.search(declaration):
                    continue
                if any(safe in declaration for safe in _SAFE_COLLECTIONS):
                    continue
                if "volatile" in mods:
                    continue
                if "final" in mods:
                    # CON-002 counter-example: final field assigned in the constructor
                    if not re.search(
                        r"\b" + re.escape(fld.name) + r"\s*=\s*new\s+" + _UNSAFE_COLL_RE.pattern,
                        class_text,
                    ):
                        continue
                writes = re.findall(
                    r"\b" + re.escape(fld.name) + r"\s*\.\s*(put|remove|add|clear|set|addAll|putAll|removeAll)\s*\(",
                    class_text,
                )
                if not writes:
                    continue
                self._emit(
                    ctx,
                    out,
                    m.path,
                    "CHM-JAVA-NAT-SHARED-MUTABLE",
                    f"Singleton bean field '{fld.name}' is a mutable non-thread-safe collection",
                    fld.line + 1,
                    fld.line + 1,
                    fld.name,
                    Category.CONCURRENCY,
                    Severity.HIGH,
                    0.8,
                    f"singleton-scoped {fld.type} field mutated via {sorted(set(writes))}",
                    {
                        "matched_snippet": self._snippet(m, fld.line + 1),
                        "line": fld.line + 1,
                        "reason": "shared mutable state in a singleton bean",
                        "field_type": fld.type,
                        "write_operations": sorted(set(writes)),
                    },
                    whole,
                )

    def _rule_semaphore_leak(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        acquire_re = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\.\s*(?:tryAcquire|acquire)\s*\(")
        for method in m.methods:
            if method.is_ctor or method.is_abstract:
                continue
            body_lines = m.skel_lines[method.open_line + 1 : method.close_line]
            body = "\n".join(body_lines)
            if "acquire" not in body:
                continue
            names = sorted({match.group(1) for match in acquire_re.finditer(body)})
            for name in names:
                if not re.search(
                    r"\bfinally\b[\s\S]{0,400}?\b" + re.escape(name) + r"\s*\.\s*release\s*\(",
                    body,
                ):
                    first = next(
                        (
                            method.open_line + 1 + idx + 1
                            for idx, ln in enumerate(body_lines)
                            if re.search(r"\b" + re.escape(name) + r"\s*\.\s*acquire\s*\(", ln)
                        ),
                        method.decl_line + 1,
                    )
                    self._emit(
                        ctx,
                        out,
                        m.path,
                        "CHM-JAVA-NAT-SEMAPHORE-LEAK",
                        f"Semaphore '{name}' is acquired without a finally release",
                        first,
                        first,
                        method.name,
                        Category.CONCURRENCY,
                        Severity.HIGH,
                        0.8,
                        "acquire() has no matching release() inside a finally block",
                        {
                            "matched_snippet": self._snippet(m, first),
                            "line": first,
                            "reason": "permit leak on the exceptional path",
                            "semaphore": name,
                        },
                        whole,
                    )

    def _rule_lock_remote_call(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for head, open_line, close_line, _header, body, _ob, _cb, _kw in self._keyword_blocks(
            m, _SYNC_ANY_RE
        ):
            if _REMOTE_CALL_RE.search(body):
                self._emit(
                    ctx,
                    out,
                    m.path,
                    "CHM-JAVA-NAT-LOCK-REMOTE-CALL",
                    "Remote/DB call performed while holding a monitor",
                    head + 1,
                    head + 1,
                    None,
                    Category.CONCURRENCY,
                    Severity.HIGH,
                    0.8,
                    "HTTP/RPC/DB invocation inside a synchronized block",
                    {
                        "matched_snippet": self._snippet(m, head + 1),
                        "line": head + 1,
                        "reason": "long external call under a lock",
                    },
                    whole,
                )

        for method in m.methods:
            body_lines = m.skel_lines[method.open_line + 1 : method.close_line]
            for idx, line in enumerate(body_lines):
                match = re.search(r"\b([A-Za-z_$][\w$]*)\s*\.\s*lock\s*\(", line)
                if match is None:
                    continue
                name = match.group(1)
                unlock_idx = None
                for j in range(idx + 1, len(body_lines)):
                    if re.search(r"\b" + re.escape(name) + r"\s*\.\s*unlock\s*\(", body_lines[j]):
                        unlock_idx = j
                        break
                if unlock_idx is None:
                    continue
                section = "\n".join(body_lines[idx : unlock_idx + 1])
                if _REMOTE_CALL_RE.search(section):
                    line_no = method.open_line + 1 + idx + 1
                    self._emit(
                        ctx,
                        out,
                        m.path,
                        "CHM-JAVA-NAT-LOCK-REMOTE-CALL",
                        f"Remote/DB call performed while holding lock '{name}'",
                        line_no,
                        line_no,
                        method.name,
                        Category.CONCURRENCY,
                        Severity.HIGH,
                        0.75,
                        "HTTP/RPC/DB invocation between lock() and unlock()",
                        {
                            "matched_snippet": self._snippet(m, line_no),
                            "line": line_no,
                            "reason": "long external call under a lock",
                            "lock": name,
                        },
                        whole,
                    )

    def _rule_double_check_no_volatile(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        text = "\n".join(m.skel_lines)
        pattern = re.compile(
            r"if\s*\(\s*([A-Za-z_$][\w$]*)\s*==\s*null\s*\)\s*\{"
            r"\s*synchronized\s*\([^)]*\)\s*\{"
            r"\s*if\s*\(\s*\1\s*==\s*null\s*\)"
        )
        for match in pattern.finditer(text):
            name = match.group(1)
            line = text[: match.start()].count("\n") + 1
            if re.search(r"\bvolatile\b[^;\n]*\b" + re.escape(name) + r"\b", text):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-DOUBLE-CHECK-NO-VOLATILE",
                f"Double-checked locking on non-volatile field '{name}'",
                line,
                line,
                name,
                Category.CONCURRENCY,
                Severity.HIGH,
                0.85,
                "double-checked locking requires a volatile field",
                {
                    "matched_snippet": self._snippet(m, line),
                    "line": line,
                    "reason": "missing volatile on a double-checked field",
                    "field": name,
                },
                whole,
            )

    def _rule_no_idempotency(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for method in m.methods:
            if method.is_ctor or method.is_abstract:
                continue
            if not self._has_annotation(method.annotations, ("RequestMapping", "PostMapping", "PutMapping", "PatchMapping")):
                continue
            body = method.body_text(m.skel_lines)
            raw_body = "\n".join(m.raw_lines[method.open_line + 1 : method.close_line])
            if not _WRITE_RE.search(body):
                continue
            if not _SIDE_EFFECT_RE.search(body):
                continue
            haystack = " ".join(
                [method.name]
                + method.params
                + [a for _l, a in method.annotations]
                + [body]
            )
            if _IDEMPOTENT_RE.search(haystack):
                continue
            money = bool(_MONEY_RE.search(haystack))
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-NO-IDEMPOTENCY",
                f"Endpoint '{method.name}' writes and calls an external system without an idempotency key",
                method.decl_line + 1,
                method.decl_line + 1,
                method.name,
                Category.CONCURRENCY,
                Severity.HIGH if money else Severity.MEDIUM,
                0.7,
                "write + external side effect with no idempotency key in name, params or annotations",
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": "non-idempotent write + external side effect",
                    "money_related": money,
                },
                whole,
            )

    # ---------------------------------------------------------- database

    def _rule_nplus1(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for head, open_line, close_line, header, body in self._loop_blocks(m):
            if not _DB_CALL_RE.search(body):
                continue
            if _DB_BATCH_RE.search(body):
                continue
            # the loop collection must come from a bulk read
            source_ok = False
            for idx in range(open_line, -1, -1):
                line = m.skel_lines[idx]
                if re.search(r"\bselectList\s*\(|\bfindAll\s*\(|\b\.list\s*\(|\bqueryForList\s*\(", line):
                    source_ok = True
                    break
                if idx < open_line - 12:
                    break
            if not source_ok:
                method = m.method_at(head)
                params_text = " ".join(method.params) if method else ""
                iterable = re.search(r":\s*([A-Za-z_$][\w$]*)", header)
                name = iterable.group(1) if iterable else ""
                if name and re.search(r"\b" + re.escape(name) + r"\b", params_text):
                    source_ok = True
            if not source_ok:
                continue
            bound = re.search(r"<\s*(\d+)\s*;", header)
            constant_bound = bool(bound) and int(bound.group(1)) <= 10
            severity = Severity.LOW if constant_bound else Severity.HIGH
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-NPLUS1",
                "Per-item database call inside a loop (N+1)",
                head + 1,
                head + 1,
                None,
                Category.DATABASE,
                severity,
                0.8 if not constant_bound else 0.55,
                "single-row query executed per iteration over a bulk-loaded collection"
                + (" (loop bound is a small compile-time constant)" if constant_bound else ""),
                {
                    "matched_snippet": self._snippet(m, head + 1),
                    "line": head + 1,
                    "reason": "N+1 query pattern",
                    "constant_bound": constant_bound,
                },
                whole,
            )

    def _rule_update_no_where(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        self._sql_no_where(ctx, m, out, whole, _SQL_UPDATE_RE, "CHM-JAVA-NAT-UPDATE-NO-WHERE", "UPDATE")

    def _rule_delete_no_where(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        self._sql_no_where(ctx, m, out, whole, _SQL_DELETE_RE, "CHM-JAVA-NAT-DELETE-NO-WHERE", "DELETE")

    def _sql_no_where(
        self,
        ctx: ScanContext,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
        pattern: "re.Pattern[str]",
        rule_id: str,
        verb: str,
    ) -> None:
        noc = "\n".join(m.noc_lines)
        for match in _STRING_LIT_RE.finditer(noc):
            sql = match.group(1)
            if not pattern.search(sql):
                continue
            if _SQL_WHERE_RE.search(sql):
                continue
            if "${" in sql:
                # dynamic MyBatis interpolation, the WHERE may live in XML
                continue
            line = noc[: match.start()].count("\n") + 1
            self._emit(
                ctx,
                out,
                m.path,
                rule_id,
                f"{verb} statement without a WHERE clause",
                line,
                line,
                None,
                Category.DATABASE,
                Severity.CRITICAL,
                0.9,
                f"inline SQL literal performs a full-table {verb}",
                {
                    "matched_snippet": sql.strip()[:300],
                    "line": line,
                    "reason": f"{verb} without WHERE",
                },
                whole,
            )

    def _rule_update_no_where_xml(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        changed_xml: list[Any],
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        self._xml_no_where(ctx, index, changed_xml, out, whole, "update", "CHM-JAVA-NAT-UPDATE-NO-WHERE")

    def _rule_delete_no_where_xml(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        changed_xml: list[Any],
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        self._xml_no_where(ctx, index, changed_xml, out, whole, "delete", "CHM-JAVA-NAT-DELETE-NO-WHERE")

    def _xml_no_where(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        changed_xml: list[Any],
        out: list[RawFinding],
        whole: bool,
        verb: str,
        rule_id: str,
    ) -> None:
        for cf in sorted(changed_xml, key=lambda c: c.path):
            text = index.side_text(cf.path) or read_text(ctx.repo_root / cf.path, max_bytes=MAX_FILE_BYTES)
            if not text:
                continue
            for match in _XML_STMT_RE.finditer(text):
                if match.group(1).lower() != verb:
                    continue
                body = match.group(3)
                if _XML_WHERE_RE.search(body):
                    continue
                if _XML_DYNAMIC_TAG_RE.search(body):
                    continue
                line = text[: match.start()].count("\n") + 1
                self._emit(
                    ctx,
                    out,
                    cf.path,
                    rule_id,
                    f"MyBatis <{verb}> '{match.group(2)}' has no WHERE clause",
                    line,
                    line,
                    match.group(2),
                    Category.DATABASE,
                    Severity.CRITICAL,
                    0.9,
                    f"mapper statement performs a full-table {verb.upper()}",
                    {
                        "matched_snippet": match.group(0).strip()[:300],
                        "line": line,
                        "reason": f"{verb.upper()} without WHERE in mapper XML",
                        "statement_id": match.group(2),
                    },
                    whole,
                )

    def _rule_tx_remote_call(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for method in m.methods:
            if not self._has_annotation(method.annotations, ("Transactional",)):
                continue
            body = method.body_text(m.skel_lines)
            if not _REMOTE_CALL_RE.search(body):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-TX-REMOTE-CALL",
                f"@Transactional method '{method.name}' performs a remote call",
                method.decl_line + 1,
                method.decl_line + 1,
                method.name,
                Category.DATABASE,
                Severity.HIGH,
                0.8,
                "HTTP/RPC call inside a transaction boundary holds the connection open",
                {
                    "matched_snippet": self._snippet(m, method.decl_line + 1),
                    "line": method.decl_line + 1,
                    "reason": "remote call inside a transaction",
                },
                whole,
            )

    def _rule_select_star(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        noc = "\n".join(m.noc_lines)
        for match in _STRING_LIT_RE.finditer(noc):
            sql = match.group(1)
            if not re.search(r"\bselect\s+\*", sql, re.I):
                continue
            if _SQL_LIMIT_RE.search(sql):
                continue
            line = noc[: match.start()].count("\n") + 1
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-SELECT-STAR",
                "SELECT * without a LIMIT",
                line,
                line,
                None,
                Category.DATABASE,
                Severity.LOW,
                0.7,
                "unbounded SELECT * projection",
                {
                    "matched_snippet": sql.strip()[:300],
                    "line": line,
                    "reason": "SELECT * with no LIMIT",
                },
                whole,
            )

    def _rule_unbounded_in(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        m: _JavaFile,
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        noc = "\n".join(m.noc_lines)
        for match in _STRING_LIT_RE.finditer(noc):
            sql = match.group(1)
            in_match = _SQL_IN_RE.search(sql)
            if in_match is None:
                continue
            inner = in_match.group(0)
            if not _SQL_PLACEHOLDER_RE.search(inner):
                continue
            line = noc[: match.start()].count("\n") + 1
            method = m.method_at(line)
            window = method.body_text(m.skel_lines) if method else ""
            if _SQL_BOUND_RE.search(window) or _SQL_BOUND_RE.search(sql):
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-UNBOUNDED-IN",
                "IN (...) built from an unbounded collection",
                line,
                line,
                method.name if method else None,
                Category.DATABASE,
                Severity.MEDIUM,
                0.65,
                "IN clause placeholder without a size guard nearby",
                {
                    "matched_snippet": sql.strip()[:300],
                    "line": line,
                    "reason": "unbounded IN list",
                },
                whole,
            )

    def _rule_dup_sql(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        models: dict[str, _JavaFile],
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        corpus = index.sql_corpus()
        groups: dict[str, list[tuple[str, int]]] = {}
        for path, line, norm in corpus:
            groups.setdefault(norm, []).append((path, line))
        changed_paths = set(models)
        for norm in sorted(groups):
            sites = groups[norm]
            files = sorted({p for p, _ in sites})
            if len(files) < 3:
                continue
            for path, line in sites:
                if path not in changed_paths:
                    continue
                self._emit(
                    ctx,
                    out,
                    path,
                    "CHM-JAVA-NAT-DUP-SQL",
                    "Identical SQL statement duplicated across mappers",
                    line,
                    line,
                    None,
                    Category.DATABASE,
                    Severity.MEDIUM,
                    0.75,
                    f"the same normalized statement appears in {len(files)} files",
                    {
                        "matched_snippet": norm[:300],
                        "line": line,
                        "reason": "duplicated SQL across mapper sites",
                        "sites": [f"{p}:{l}" for p, l in sites],
                    },
                    whole,
                )

    # ------------------------------------------------------- performance

    def _rule_on2(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        loops = self._loop_blocks(m)
        linear_re = re.compile(
            r"\b([A-Za-z_$][\w$]*)\s*\.\s*(contains|indexOf|lastIndexOf)\s*\("
            r"|\b([A-Za-z_$][\w$]*)\s*\.\s*stream\s*\(\s*\)\s*\.\s*anyMatch\s*\("
            r"|\b([A-Za-z_$][\w$]*)\s*\.\s*remove\s*\(\s*[A-Za-z_$]"
        )
        for outer_head, outer_open, outer_close, _outer, _ob in loops:
            for inner_head, inner_open, inner_close, _inner, body in loops:
                if inner_open <= outer_open or inner_close >= outer_close:
                    continue
                for match in linear_re.finditer(body):
                    name = match.group(1) or match.group(3) or match.group(4)
                    if not name:
                        continue
                    if re.search(r"\b" + re.escape(name) + r"\s*\.\s*containsKey\s*\(", body):
                        # PERF-002 counter-example: hash lookup is O(1)
                        continue
                    decl = re.search(
                        r"\b(HashMap|HashSet|Map|Set|TreeMap|TreeSet|ConcurrentHashMap|LinkedHashMap|LinkedHashSet)\b[^;\n]*\b"
                        + re.escape(name)
                        + r"\b",
                        "\n".join(m.skel_lines),
                    )
                    if decl is not None:
                        continue
                    literal = re.search(
                        r"\b" + re.escape(name) + r"\s*=\s*(?:Arrays\s*\.\s*asList|List\s*\.\s*of|Set\s*\.\s*of)\s*\(([^)]*)\)",
                        "\n".join(m.skel_lines),
                    )
                    if literal is not None and literal.group(1).count(",") <= 10:
                        continue
                    outer_decl = re.search(
                        r"\b(List|ArrayList|LinkedList)\b[^;\n]*\b",
                        "\n".join(m.skel_lines),
                    )
                    perf = PerfConfidence.LIKELY if outer_decl else PerfConfidence.SUSPECTED
                    line = inner_open + 1
                    self._emit(
                        ctx,
                        out,
                        m.path,
                        "CHM-JAVA-NAT-ON2",
                        f"Linear scan of '{name}' inside a nested loop",
                        line,
                        line,
                        None,
                        Category.PERFORMANCE,
                        Severity.MEDIUM,
                        0.6,
                        "nested loop with a linear membership test on a list",
                        {
                            "matched_snippet": self._snippet(m, line),
                            "line": line,
                            "reason": "quadratic membership test",
                            "perf_confidence": perf.value,
                            "collection": name,
                        },
                        whole,
                    )
                    break

    def _rule_repeat_serialize(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for method in m.methods:
            if method.is_ctor or method.is_abstract:
                continue
            body = method.body_text(m.skel_lines)
            if not body:
                continue
            counts: dict[str, list[int]] = {}
            base_line = method.open_line + 1
            for idx, line in enumerate(m.skel_lines[method.open_line + 1 : method.close_line]):
                for match in _SERIALIZE_RE.finditer(line):
                    target = " ".join(match.group(1).split())
                    counts.setdefault(target, []).append(base_line + idx + 1)
            for target in sorted(counts):
                lines = counts[target]
                if len(lines) < 3:
                    continue
                self._emit(
                    ctx,
                    out,
                    m.path,
                    "CHM-JAVA-NAT-REPEAT-SERIALIZE",
                    f"Object '{target}' serialized {len(lines)} times in one method",
                    lines[0],
                    lines[-1],
                    method.name,
                    Category.PERFORMANCE,
                    Severity.MEDIUM,
                    0.75,
                    "the same object is serialized repeatedly inside one method body",
                    {
                        "matched_snippet": self._snippet(m, lines[0]),
                        "line": lines[0],
                        "reason": "repeated serialization of the same object",
                        "count": len(lines),
                        "target": target,
                    },
                    whole,
                )

    # ------------------------------------------------------- testability

    def _rule_hardcoded_time(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        if TEST_PATH_RE.search(m.path):
            return
        text = "\n".join(m.skel_lines)
        if _CLOCK_SUPPRESS_RE.search(text):
            return
        for cls in m.classes:
            name = cls.name
            if re.search(r"(?:Test|Tests|Config|Configuration|Util|Utils)$", name):
                continue
            class_text = "\n".join(m.skel_lines[cls.open_line : cls.close_line + 1])
            calls = _TIME_CALL_RE.findall(class_text)
            if len(calls) <= 2:
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-HARDCODED-TIME",
                f"Class '{name}' reads the wall clock {len(calls)} times directly",
                cls.decl_line + 1,
                cls.decl_line + 1,
                name,
                Category.TESTABILITY,
                Severity.MEDIUM,
                0.7,
                "no injectable Clock/LocalDate and more than two direct time reads",
                {
                    "matched_snippet": self._snippet(m, cls.decl_line + 1),
                    "line": cls.decl_line + 1,
                    "reason": "time is not injectable",
                    "time_calls": len(calls),
                },
                whole,
            )

    def _rule_global_mutable_singleton(
        self, ctx: ScanContext, m: _JavaFile, out: list[RawFinding], whole: bool
    ) -> None:
        for fld in m.fields:
            mods = fld.mods.split()
            if "public" not in mods or "static" not in mods:
                continue
            if "final" in mods:
                continue
            if re.match(r"^(?:Logger|Log)$", fld.type) or "Logger" in fld.type:
                continue
            if fld.name.isupper():
                continue
            self._emit(
                ctx,
                out,
                m.path,
                "CHM-JAVA-NAT-GLOBAL-MUTABLE-SINGLETON",
                f"Public static mutable field '{fld.name}'",
                fld.line + 1,
                fld.line + 1,
                fld.name,
                Category.TESTABILITY,
                Severity.MEDIUM,
                0.75,
                "global mutable state defeats test isolation",
                {
                    "matched_snippet": self._snippet(m, fld.line + 1),
                    "line": fld.line + 1,
                    "reason": "public static non-final field",
                    "field_type": fld.type,
                },
                whole,
            )

    # ------------------------------------------------------- duplication

    def _rule_duplicate_block(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        models: dict[str, _JavaFile],
        out: list[RawFinding],
        whole: bool,
        min_tokens: int,
    ) -> None:
        paths = [p for p in index.java_paths()][:MAX_DUP_FILES]
        token_map: dict[str, tuple[list[str], list[int]]] = {}
        for rel in paths:
            tokens, lines = index.tokens_for(rel)
            if tokens:
                token_map[rel] = (tokens, lines)
        if not token_map:
            return

        occurrence_index: dict[tuple[str, ...], list[tuple[str, int]]] = {}
        for rel in sorted(token_map):
            tokens, _lines = token_map[rel]
            limit = len(tokens) - DUP_WINDOW + 1
            for start in range(0, max(0, limit), DUP_STEP):
                key = tuple(tokens[start : start + DUP_WINDOW])
                bucket = occurrence_index.get(key)
                if bucket is None:
                    occurrence_index[key] = [(rel, start)]
                elif len(bucket) < 6:
                    bucket.append((rel, start))

        changed_paths = set(models)
        blocks: dict[tuple[str, int], tuple[str, int, int, str, int]] = {}
        for key in sorted(occurrence_index):
            occurrences = occurrence_index[key]
            if len(occurrences) < 2:
                continue
            for a in range(len(occurrences)):
                for b in range(a + 1, len(occurrences)):
                    path_a, start_a = occurrences[a]
                    path_b, start_b = occurrences[b]
                    if path_a == path_b and abs(start_a - start_b) < DUP_WINDOW:
                        continue
                    tokens_a = token_map[path_a][0]
                    tokens_b = token_map[path_b][0]
                    length = DUP_WINDOW
                    while (
                        start_a + length < len(tokens_a)
                        and start_b + length < len(tokens_b)
                        and tokens_a[start_a + length] == tokens_b[start_b + length]
                    ):
                        length += 1
                    if length < min_tokens:
                        continue
                    if path_a in changed_paths:
                        blocks.setdefault(
                            (path_a, start_a), (path_a, start_a, length, path_b, start_b)
                        )
                    if path_b in changed_paths:
                        blocks.setdefault(
                            (path_b, start_b), (path_b, start_b, length, path_a, start_a)
                        )

        merged: dict[str, list[tuple[int, int, int, str, int]]] = {}
        for key in sorted(blocks):
            path, start, length, other_path, other_start = blocks[key]
            merged.setdefault(path, []).append((start, length, length, other_path, other_start))

        for path in sorted(merged):
            spans = sorted(merged[path], key=lambda x: (x[0], x[1]))
            groups: list[list[tuple[int, int, int, str, int]]] = []
            for span in spans:
                if groups and span[0] <= groups[-1][-1][0] + groups[-1][-1][1]:
                    groups[-1].append(span)
                else:
                    groups.append([span])
            model = models.get(path)
            if model is None:
                continue
            tokens, lines = token_map[path]
            emitted = 0
            for group in groups:
                if emitted >= MAX_FINDINGS_PER_RULE_PER_FILE:
                    break
                start = group[0][0]
                end = max(item[0] + item[1] for item in group)
                length = end - start
                if length < min_tokens:
                    continue
                block_tokens = tokens[start:end]
                if self._dup_is_trivial(model, block_tokens, start, end, lines):
                    continue
                start_line = lines[start] if start < len(lines) else 1
                end_line = lines[min(end - 1, len(lines) - 1)] if lines else start_line
                other = group[0][3]
                self._emit(
                    ctx,
                    out,
                    path,
                    "CHM-JAVA-NAT-DUPLICATE-BLOCK",
                    f"{length} duplicated tokens",
                    start_line,
                    end_line,
                    None,
                    Category.DUPLICATION,
                    Severity.MEDIUM,
                    0.75,
                    f"normalized token window repeated in {other}",
                    {
                        "matched_snippet": self._snippet(model, start_line),
                        "line": start_line,
                        "reason": "identical normalized token block found elsewhere",
                        "duplicate_tokens": length,
                        "duplicate_of": other,
                    },
                    whole,
                )
                emitted += 1

    @staticmethod
    def _dup_is_trivial(
        model: _JavaFile,
        block_tokens: list[str],
        start: int,
        end: int,
        lines: list[int],
    ) -> bool:
        tokens = block_tokens
        has_branch = any(t in _BRANCH_TOKENS for t in tokens)
        if not has_branch and len(tokens) < 120:
            return True
        if "(" not in tokens:
            return True
        if "case" in tokens and not any(t in tokens for t in ("if", "for", "while", "do", "catch")):
            return True
        if lines:
            names = set()
            first_line = lines[start] if start < len(lines) else 1
            last_line = lines[min(end - 1, len(lines) - 1)]
            for line_no in (first_line, last_line):
                method = model.method_at(line_no - 1)
                if method is not None:
                    names.add(method.name)
            if names and names <= {"equals", "hashCode", "toString"}:
                return True
            if names and all(
                n.startswith(("get", "set", "is")) and len(n) > 3 for n in names
            ):
                return True
        return False

    def _rule_duplicate_business_rule(
        self,
        ctx: ScanContext,
        index: _RepoIndex,
        models: dict[str, _JavaFile],
        out: list[RawFinding],
        whole: bool,
    ) -> None:
        groups: dict[str, list[tuple[str, int, str]]] = {}
        for path in sorted(models):
            model = models[path]
            noc = "\n".join(model.noc_lines)
            for match in _IF_PAREN_RE.finditer(noc):
                open_idx = match.end() - 1
                depth = 0
                cursor = open_idx
                while cursor < len(noc):
                    ch = noc[cursor]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    cursor += 1
                if cursor >= len(noc):
                    continue
                expr = noc[open_idx + 1 : cursor]
                normalized = self._normalize_condition(expr)
                if not normalized:
                    continue
                line = noc[: match.start()].count("\n") + 1
                method = model.method_at(line - 1)
                method_name = method.name if method else "?"
                groups.setdefault(normalized, []).append((path, line, method_name))

        for normalized in sorted(groups):
            sites = groups[normalized]
            methods = {(p, m) for p, _l, m in sites}
            if len(methods) < 3:
                continue
            if re.fullmatch(r"[A-Za-z_$][\w$]*\s*(?:==|!=)\s*null", normalized):
                continue
            has_double_logic = normalized.count("&&") + normalized.count("||") >= 2
            has_state_literal = bool(
                re.search(r"(?:==|!=)\s*(?:STR|NUM|true|false)", normalized)
            )
            if not (has_double_logic or has_state_literal):
                continue
            for path, line, method_name in sites:
                if path not in models:
                    continue
                self._emit(
                    ctx,
                    out,
                    path,
                    "CHM-JAVA-NAT-DUPLICATE-BUSINESS-RULE",
                    "Business rule duplicated across three or more methods",
                    line,
                    line,
                    method_name,
                    Category.DUPLICATION,
                    Severity.MEDIUM,
                    0.7,
                    f"identical condition in {len(methods)} distinct methods",
                    {
                        "matched_snippet": normalized[:300],
                        "line": line,
                        "reason": "the same business condition is copy-pasted",
                        "occurrences": [f"{p}:{l}" for p, l, _ in sites],
                    },
                    whole,
                )

    @staticmethod
    def _normalize_condition(expr: str) -> str:
        text = " ".join(expr.split())
        text = re.sub(r"\"(?:\\.|[^\"\\])*\"", "STR", text)
        text = re.sub(r"'(?:\\.|[^'\\])*'", "STR", text)
        text = re.sub(r"\b\d+(?:\.\d+)?[fFdDlL]?\b", "NUM", text)
        return text.strip()

    # -------------------------------------------------------- not implemented

    def _rule_no_cache_not_implemented(self) -> None:
        """CHM-JAVA-NAT-NO-CACHE-HIGH-FREQ is deliberately absent.

        Spec CHM-PERF-004 forbids reporting "there is no cache" as a defect:
        the absence of a cache is not a static, provable property of the code,
        so any such finding would be a pure false positive.  This stub exists
        only so the omission is discoverable in the source.
        """
        return None


__all__ = ["JavaNativeAnalyzer", "PROVIDER_NAME"]
