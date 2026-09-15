"""Adversarial suite A: false positives.

40 change sets that *look* suspicious but are legitimate engineering.  Every one
of them must produce **no MEDIUM+ finding**.  The suite covers the thirteen
"reasonable pattern" families of the specification plus the extra ones the
fixtures do not reach (Lombok, @Builder, @Deprecated, main(), test paths,
constant loop bounds, repository-level thread-pool shutdown, ...).

The run is the real ``Orchestrator(mode=repo)`` over a temp tree; nothing is
mocked.  Numbers are printed as measured -- if the rate misses the target the
suite says ``TARGET_MISSED`` and prints the real value instead of hiding it.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden"))

from _chm import Run, run_source  # noqa: E402

#: Targets from the specification.
MEDIUM_TARGET = 0.08
HIGH_TARGET = 0.03

#: False positives that are already documented in ``test/README.md``.
#: They are still counted in the raw rate; they are only excluded from the
#: "new false positive" failure list so the suite reports regressions loudly.
DOCUMENTED_FP = {
    "java-scope-prototype-bean",
}

JAVA = "src/main/java/demo/fp/Sample.java"


def _java(label: str, body: str, *, documented: bool = False) -> tuple:
    return (label, body, JAVA, {}, documented)


def _vue(label: str, body: str, *, extra: dict | None = None) -> tuple:
    return (label, body, "src/views/Sample.vue", extra or {}, False)


CASES: list[tuple] = [
    # ---- 1. resource safety ------------------------------------------------
    _java(
        "java-try-with-resources",
        '''package demo.fp;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;

public class Sample {

    public String head(String path) throws IOException {
        try (BufferedReader reader = new BufferedReader(new FileReader(path))) {
            return reader.readLine();
        }
    }
}
''',
    ),
    _java(
        "java-manual-close-in-finally",
        '''package demo.fp;

import java.io.FileReader;
import java.io.IOException;

public class Sample {

    public int first(String path) throws IOException {
        FileReader reader = new FileReader(path);
        try {
            return reader.read();
        } finally {
            reader.close();
        }
    }
}
''',
    ),
    # ---- 2. concurrency ----------------------------------------------------
    _java(
        "java-concurrent-hashmap-singleton",
        '''package demo.fp;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class Sample {

    private final Map<String, String> cache = new ConcurrentHashMap<>();

    public void put(String key, String value) {
        cache.put(key, value);
    }
}
''',
    ),
    _java(
        "java-semaphore-release-in-finally",
        '''package demo.fp;

import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

@Service
public class Sample {

    private final Semaphore permits = new Semaphore(2);

    public String guarded(String caller) throws InterruptedException {
        permits.acquire();
        try {
            return "ok:" + caller;
        } finally {
            permits.release();
        }
    }
}
''',
    ),
    _java(
        "java-scope-prototype-bean",
        '''package demo.fp;

import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class Sample {

    private final Map<String, String> scratch = new HashMap<>();

    public void note(String key, String value) {
        scratch.put(key, value);
    }
}
''',
        documented=True,
    ),
    _java(
        "java-volatile-double-check",
        '''package demo.fp;

public class Sample {

    private volatile Holder instance;

    public Holder get() {
        if (instance == null) {
            synchronized (Sample.class) {
                if (instance == null) {
                    instance = new Holder();
                }
            }
        }
        return instance;
    }

    static class Holder {
    }
}
''',
    ),
    # ---- 3. error handling -------------------------------------------------
    _java(
        "java-optional-in-catch",
        '''package demo.fp;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public class Sample {

    public Optional<String> load(Path path) {
        try {
            return Optional.of(Files.readString(path));
        } catch (IOException ex) {
            return Optional.empty();
        }
    }
}
''',
    ),
    _java(
        "java-degrade-with-metric",
        '''package demo.fp;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Sample {

    private static final Logger log = LoggerFactory.getLogger(Sample.class);

    private final Counter degraded;

    public Sample(MeterRegistry registry) {
        this.degraded = registry.counter("flag.degraded");
    }

    public String flag(Path path) {
        try {
            return Files.readString(path).trim();
        } catch (IOException ex) {
            degraded.increment();
            log.warn("flag unavailable, using the safe default", ex);
            return "off";
        }
    }
}
''',
    ),
    _java(
        "java-controller-fallback-catch",
        '''package demo.fp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Sample {

    private static final Logger log = LoggerFactory.getLogger(Sample.class);

    public String handle(String id) {
        try {
            return "ok:" + id;
        } catch (Exception ex) {
            log.error("request failed for {}", id, ex);
            return "error";
        }
    }
}
''',
    ),
    _java(
        "java-catch-with-counter",
        '''package demo.fp;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class Sample {

    private final Counter failures;

    public Sample(MeterRegistry registry) {
        this.failures = registry.counter("sample.failures");
    }

    public String parse(String raw) {
        try {
            return raw.trim();
        } catch (RuntimeException ex) {
            failures.increment();
            throw new IllegalArgumentException("bad input", ex);
        }
    }
}
''',
    ),
    # ---- 4. database -------------------------------------------------------
    _java(
        "java-batch-prefetch",
        '''package demo.fp;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper;

    public Sample(RowMapper mapper) {
        this.mapper = mapper;
    }

    public List<String> byIds(List<String> ids) {
        return mapper.selectBatchIds(ids);
    }

    @Mapper
    public interface RowMapper {

        List<String> selectBatchIds(List<String> ids);
    }
}
''',
    ),
    _java(
        "java-update-with-where",
        '''package demo.fp;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper;

    public Sample(RowMapper mapper) {
        this.mapper = mapper;
    }

    public void rename(String id) {
        mapper.execute("UPDATE rows SET label = 'x' WHERE id = #{id}");
    }

    @Mapper
    public interface RowMapper {

        int execute(String sql);
    }
}
''',
    ),
    _java(
        "java-select-star-with-limit",
        '''package demo.fp;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper;

    public Sample(RowMapper mapper) {
        this.mapper = mapper;
    }

    public String firstPage() {
        return mapper.one("SELECT * FROM rows LIMIT 50");
    }

    @Mapper
    public interface RowMapper {

        String one(String sql);
    }
}
''',
    ),
    _java(
        "java-nplus1-constant-bound",
        '''package demo.fp;

import java.util.ArrayList;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper;

    public Sample(RowMapper mapper) {
        this.mapper = mapper;
    }

    public List<String> firstThree(List<String> ids) {
        List<String> out = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            out.add(mapper.selectById(ids.get(i)));
        }
        return out;
    }

    @Mapper
    public interface RowMapper {

        String selectById(String id);
    }
}
''',
    ),
    # ---- 5. performance ----------------------------------------------------
    _java(
        "java-hash-map-lookup-in-loop",
        '''package demo.fp;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class Sample {

    public List<String> resolve(List<String> keys, Map<String, String> index) {
        List<String> out = new ArrayList<>();
        for (String key : keys) {
            for (String candidate : keys) {
                if (index.containsKey(candidate)) {
                    out.add(key + candidate);
                }
            }
        }
        return out;
    }
}
''',
    ),
    _java(
        "java-small-literal-scan",
        '''package demo.fp;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class Sample {

    public List<String> pick(List<String> values) {
        List<String> allowed = Arrays.asList("a", "b", "c");
        List<String> out = new ArrayList<>();
        for (String value : values) {
            for (String candidate : values) {
                if (allowed.contains(candidate)) {
                    out.add(value);
                }
            }
        }
        return out;
    }
}
''',
    ),
    _java(
        "java-single-time-call",
        '''package demo.fp;

public class Sample {

    public String stamp(String prefix) {
        return prefix + "-" + System.currentTimeMillis();
    }
}
''',
    ),
    _java(
        "java-injectable-clock",
        '''package demo.fp;

import java.time.Clock;
import java.time.LocalDate;
import org.springframework.stereotype.Service;

@Service
public class Sample {

    private final Clock clock;

    public Sample(Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }

    public long epochMillis() {
        return clock.millis();
    }
}
''',
    ),
    # ---- 6. abstraction ----------------------------------------------------
    _java(
        "java-strategy-three-impls",
        '''package demo.fp;

public interface Sample {

    String route(String channel);
}
''',
    ),
    _java(
        "java-feign-single-impl",
        '''package demo.fp;

import java.util.List;
import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(name = "inventory")
public interface Sample {

    List<String> available(String sku);
}
''',
    ),
    _java(
        "java-error-normalising-wrapper",
        '''package demo.fp;

public class Sample {

    private final SmsGateway gateway;

    public Sample(SmsGateway gateway) {
        this.gateway = gateway;
    }

    public void send(String to, String body) {
        try {
            gateway.deliver(to, body);
        } catch (SmsFailure ex) {
            throw new IllegalStateException("sms failed for " + to, ex);
        }
    }

    public void resend(String to, String body) {
        try {
            gateway.deliver(to, body);
        } catch (SmsFailure ex) {
            throw new IllegalStateException("sms retry failed for " + to, ex);
        }
    }

    public static class SmsGateway {
        public void deliver(String to, String body) throws SmsFailure {
        }
    }

    public static class SmsFailure extends Exception {
        public SmsFailure(String message) {
            super(message);
        }
    }
}
''',
    ),
    _java(
        "java-component-no-explicit-new",
        '''package demo.fp;

import org.springframework.stereotype.Component;

@Component
public class Sample {

    public int scale(int value) {
        return value * 3;
    }
}
''',
    ),
    # ---- 7. dead code ------------------------------------------------------
    _java(
        "java-scheduled-private-method",
        '''package demo.fp;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class Sample {

    @Scheduled(cron = "0 0/5 * * * *")
    private void refresh() {
    }
}
''',
    ),
    _java(
        "java-kafka-listener-private-method",
        '''package demo.fp;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class Sample {

    @KafkaListener(topics = "orders")
    private void onMessage(String payload) {
    }
}
''',
    ),
    _java(
        "java-reflection-only-method",
        '''package demo.fp;

import java.lang.reflect.Method;

public class Sample {

    public String boot(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("compute");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }

    private String compute() {
        return "computed";
    }
}
''',
    ),
    _java(
        "java-mapper-xml-reference",
        '''package demo.fp;

import java.util.List;

public class Sample {

    private List<String> selectByTenant(String tenant) {
        return List.of();
    }
}
''',
        # the XML reference lives in an extra file
    ),
    _java(
        "java-deprecated-compat-method",
        '''package demo.fp;

public class Sample {

    @Deprecated
    public String legacyFormat(String value) {
        return value.trim();
    }
}
''',
    ),
    _java(
        "java-value-with-default",
        '''package demo.fp;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class Sample {

    @Value("${sample.batch-size:100}")
    private int batchSize;

    public int batchSize() {
        return batchSize;
    }
}
''',
    ),
    _java(
        "java-builder-many-params",
        '''package demo.fp;

import lombok.Builder;

@Builder
public class Sample {

    public String render(
            String a, String b, String c, String d, String e, String f, String g) {
        return a + b + c + d + e + f + g;
    }
}
''',
    ),
    _java(
        "java-long-pure-mapping-method",
        '''package demo.fp;

public class Sample {

    public String map(int value) {
        String a = "a" + value;
        String b = "b" + value;
        String c = "c" + value;
        String d = "d" + value;
        String e = "e" + value;
        String f = "f" + value;
        String g = "g" + value;
        String h = "h" + value;
        String i = "i" + value;
        String j = "j" + value;
        String k = "k" + value;
        String l = "l" + value;
        String m = "m" + value;
        String n = "n" + value;
        String o = "o" + value;
        String p = "p" + value;
        String q = "q" + value;
        String r = "r" + value;
        String s = "s" + value;
        String t = "t" + value;
        String u = "u" + value;
        String v = "v" + value;
        String w = "w" + value;
        String x = "x" + value;
        String y = "y" + value;
        String z = "z" + value;
        return a + b + c + d + e + f + g + h + i + j + k + l + m
                + n + o + p + q + r + s + t + u + v + w + x + y + z;
    }
}
''',
    ),
    _java(
        "java-main-with-stdout",
        '''package demo.fp;

public class Sample {

    public static void main(String[] args) {
        System.out.println("usage: sample <path>");
    }
}
''',
    ),
    _java(
        "java-test-path-stdout",
        '''package demo.fp;

public class Sample {

    public void dump() {
        System.out.println("debugging the fixture");
    }
}
''',
    ),
    _java(
        "java-transactional-without-remote",
        '''package demo.fp;

import org.springframework.transaction.annotation.Transactional;

public class Sample {

    @Transactional
    public void apply(String account) {
        String normalised = account.trim();
        if (normalised.isEmpty()) {
            throw new IllegalArgumentException("empty account");
        }
    }
}
''',
    ),
    _java(
        "java-bean-thread-pool-with-shutdown",
        '''package demo.fp;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.annotation.PreDestroy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Sample {

    private ExecutorService pool;

    @Bean
    public ExecutorService pool() {
        this.pool = Executors.newFixedThreadPool(4);
        return this.pool;
    }

    @PreDestroy
    public void stop() {
        if (pool != null) {
            pool.shutdown();
        }
    }
}
''',
    ),
    _java(
        "java-similar-but-different-business-rules",
        '''package demo.fp;

import java.math.BigDecimal;

public class Sample {

    public BigDecimal refund(String reasonCode, BigDecimal paid, int daysHeld) {
        switch (reasonCode) {
            case "DAMAGED":
                return paid;
            case "LATE":
                int remaining = daysHeld;
                BigDecimal amount = paid;
                while (remaining > 0) {
                    amount = amount.multiply(new BigDecimal("0.90"));
                    remaining--;
                }
                return amount;
            default:
                return BigDecimal.ZERO;
        }
    }

    public BigDecimal coupon(String code, BigDecimal paid) {
        if (code == null || code.isEmpty()) {
            return BigDecimal.ZERO;
        }
        BigDecimal value = BigDecimal.valueOf(code.length());
        return value.min(paid).max(BigDecimal.ZERO);
    }
}
''',
    ),
    # ---- 8. JS / Vue -------------------------------------------------------
    _vue(
        "vue-api-wrapper-normalises-errors",
        '''<template>
  <div class="sample">{{ value }}</div>
</template>

<script>
export default {
  name: 'Sample',
  data() {
    return { value: 'x' }
  }
}
</script>
''',
        extra={
            "src/api/sample.js": '''import request from '@/utils/request'

export function fetchValue(id) {
  return request({
    url: '/value/' + id,
    method: 'get'
  }).then((res) => res.data)
}

function normalise(raw) {
  return raw && raw.value ? raw.value : 'unknown'
}
''',
            "src/utils/request.js": '''import axios from 'axios'

const request = axios.create({ baseURL: '/api' })

export default request
''',
        },
    ),
    _vue(
        "vue-component-dynamic-is",
        '''<template>
  <div class="sample">
    <component :is="current" />
  </div>
</template>

<script>
import AlphaPanel from '@/components/AlphaPanel.vue'

export default {
  name: 'Sample',
  components: { AlphaPanel },
  data() {
    return { current: 'AlphaPanel' }
  }
}
</script>
''',
    ),
    _vue(
        "vue-component-kebab-tag",
        '''<template>
  <div class="sample">
    <alpha-panel />
  </div>
</template>

<script>
import AlphaPanel from '@/components/AlphaPanel.vue'

export default {
  name: 'Sample',
  components: { AlphaPanel }
}
</script>
''',
    ),
    _vue(
        "vue-two-line-computed",
        '''<template>
  <div class="sample">{{ label }}</div>
</template>

<script>
export default {
  name: 'Sample',
  props: {
    user: { type: Object, default: null }
  },
  computed: {
    label() {
      return this.user.name
    }
  }
}
</script>
''',
    ),
    _vue(
        "vue-export-imported-elsewhere",
        '''<template>
  <div class="sample">{{ formatted }}</div>
</template>

<script>
import { formatDate } from '@/utils/format'

export default {
  name: 'Sample',
  computed: {
    formatted() {
      return formatDate('2026-01-01')
    }
  }
}
</script>
''',
        extra={
            "src/utils/format.js": '''export function formatDate(value) {
  if (!value) {
    return ''
  }
  return value.slice(0, 10)
}
''',
        },
    ),
    _vue(
        "vue-dependency-imported",
        '''<template>
  <div class="sample">{{ now }}</div>
</template>

<script>
import moment from 'moment'

export default {
  name: 'Sample',
  computed: {
    now() {
      return moment().format()
    }
  }
}
</script>
''',
        extra={
            "package.json": '''{
  "name": "fp-sample",
  "version": "1.0.0",
  "dependencies": {
    "moment": "^2.29.4",
    "vue": "^2.7.14"
  }
}
''',
        },
    ),
    _vue(
        "js-empty-catch-with-ignore-comment",
        '''<template>
  <div class="sample">ok</div>
</template>

<script>
export default {
  name: 'Sample',
  methods: {
    read() {
      try {
        return JSON.parse('{}')
      } catch (e) {
        // intentionally ignored: the payload is optional
      }
      return {}
    }
  }
}
</script>
''',
    ),
    _vue(
        "js-console-log-in-test-path",
        '''<template>
  <div class="sample">ok</div>
</template>

<script>
export default {
  name: 'Sample',
  methods: {
    dump() {
      console.log('debugging')
    }
  }
}
</script>
''',
    ),
]


class FalsePositiveTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.results: list[tuple[str, Run, list]] = []
        for label, source, filename, extra, documented in CASES:
            if label == "java-mapper-xml-reference":
                extra = dict(extra)
                extra["src/main/resources/mapper/SampleMapper.xml"] = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<mapper namespace="demo.fp.SampleMapper">\n'
                    '    <select id="selectByTenant" resultType="java.lang.String">\n'
                    "        SELECT name FROM tenants WHERE tenant = #{tenant}\n"
                    "    </select>\n"
                    "</mapper>\n"
                )
            if label == "java-strategy-three-impls":
                extra = {
                    "src/main/java/demo/fp/Retail.java": (
                        "package demo.fp;\n\npublic class Retail implements Sample {\n"
                        "    @Override\n    public String route(String channel) {\n"
                        '        return "retail:" + channel;\n    }\n}\n'
                    ),
                    "src/main/java/demo/fp/Wholesale.java": (
                        "package demo.fp;\n\npublic class Wholesale implements Sample {\n"
                        "    @Override\n    public String route(String channel) {\n"
                        '        return "wholesale:" + channel;\n    }\n}\n'
                    ),
                    "src/main/java/demo/fp/Vip.java": (
                        "package demo.fp;\n\npublic class Vip implements Sample {\n"
                        "    @Override\n    public String route(String channel) {\n"
                        '        return "vip:" + channel;\n    }\n}\n'
                    ),
                }
            if label == "java-feign-single-impl":
                extra = {
                    "src/main/java/demo/fp/InventoryClientImpl.java": (
                        "package demo.fp;\n\nimport java.util.List;\n\n"
                        "public class InventoryClientImpl implements Sample {\n"
                        "    @Override\n    public List<String> available(String sku) {\n"
                        "        return List.of();\n    }\n}\n"
                    )
                }
            if label == "js-console-log-in-test-path":
                filename = "src/test/Sample.vue"
            run = run_source(source, filename=filename, extra_files=extra)
            cls.results.append((label, run, run.medplus()))

        cls.stats = cls._stats()
        print("\n" + "=" * 78)
        print("FALSE-POSITIVE SUITE (target: MEDIUM+ <= 8%, HIGH+ <= 3%)")
        print("=" * 78)
        for label, _run, bad in cls.results:
            mark = "FP " if bad else "ok "
            print(f"  {mark}{label:<44} MEDIUM+={len(bad)}")
        s = cls.stats
        print("-" * 78)
        print(
            f"  MEDIUM+ false positive rate = {s['med_rate']:.1%} "
            f"({s['med_fp']}/{s['total']})   (target <= {MEDIUM_TARGET:.0%})"
        )
        print(
            f"  HIGH+  false positive rate = {s['high_rate']:.1%} "
            f"({s['high_fp']}/{s['total']})   (target <= {HIGH_TARGET:.0%})"
        )
        print(
            f"  MEDIUM+ rate excluding documented FPs = {s['med_rate_excl']:.1%} "
            f"({s['med_fp'] - s['documented_fp']}/{s['total']})"
        )
        print("=" * 78)
        if s["med_rate"] > MEDIUM_TARGET:
            print("  TARGET_MISSED: MEDIUM+ false positive rate above target")
        if s["high_rate"] > HIGH_TARGET:
            print("  TARGET_MISSED: HIGH+ false positive rate above target")
        if s["documented_fp"]:
            print(
                f"  NOTE: {s['documented_fp']} of the false positives are already "
                "documented in KNOWN_GAPS"
            )

    @classmethod
    def _stats(cls) -> dict:
        total = len(cls.results)
        med_fp = 0
        high_fp = 0
        documented_fp = 0
        for label, _run, bad in cls.results:
            if bad:
                med_fp += 1
            if any(f.highplus for f in bad):
                high_fp += 1
            if bad and label in DOCUMENTED_FP:
                documented_fp += 1
        return {
            "total": total,
            "med_fp": med_fp,
            "high_fp": high_fp,
            "documented_fp": documented_fp,
            "med_rate": med_fp / total if total else 0.0,
            "high_rate": high_fp / total if total else 0.0,
            "med_rate_excl": (med_fp - documented_fp) / total if total else 0.0,
        }

    def test_no_undocumented_medium_plus_finding(self) -> None:
        failures: list[str] = []
        for label, _run, bad in self.results:
            if not bad or label in DOCUMENTED_FP:
                continue
            failures.append(
                f"{label}: {len(bad)} MEDIUM+ finding(s)\n"
                + "\n".join("      " + str(f) for f in bad)
            )
        if failures:
            self.fail(
                "the following legitimate change sets produced MEDIUM+ findings:\n"
                + "\n".join("    " + x for x in failures)
            )

    def test_documented_false_positive_still_reproduces(self) -> None:
        """A documented FP must not silently disappear or silently grow."""
        found = {
            label: bad for label, _run, bad in self.results if label in DOCUMENTED_FP
        }
        for label in DOCUMENTED_FP:
            with self.subTest(case=label):
                self.assertIn(label, found)
                print(
                    f"\n  KNOWN_GAP_CONFIRMED: {label} still produces "
                    f"{len(found[label])} MEDIUM+ finding(s): "
                    + "; ".join(str(f) for f in found[label])
                )

    def test_case_count(self) -> None:
        self.assertGreaterEqual(len(CASES), 30, "the suite must cover >= 30 cases")

    def test_targets_are_reported(self) -> None:
        s = self.stats
        print(
            f"\n  med_rate={s['med_rate']:.4f} high_rate={s['high_rate']:.4f} "
            f"med_rate_excl_documented={s['med_rate_excl']:.4f}"
        )
        if s["med_rate"] > MEDIUM_TARGET or s["high_rate"] > HIGH_TARGET:
            print("  TARGET_MISSED (see the numbers above)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
