"""Adversarial suite B: false negatives.

36 genuine defects -- one per implemented rule family -- that the engine MUST
detect.  Each case is a small, realistic change set; the assertion is that the
expected ``rule_id`` appears in the run (either in the end-to-end report or in
the raw provider output when a later stage merged it away).

Reported as measured:

* ``HIGH/CRITICAL recall`` (target >= 95%)
* ``all-severity recall``  (target >= 85%)
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden"))

from _chm import golden_config, run_source  # noqa: E402

HIGH_TARGET = 0.95
ALL_TARGET = 0.85

JAVA = "src/main/java/demo/fn/Sample.java"

#: (label, source, filename, expected rule_id, expected severity, extra files, config)
CASES: list[tuple] = []


def case(label, source, rule, severity, *, filename=JAVA, extra=None, config=None):
    CASES.append((label, source, filename, rule, severity, extra or {}, config))


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------
case(
    "fn-empty-catch",
    '''package demo.fn;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Sample {

    public String read(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException ex) {
        }
        return "";
    }
}
''',
    "CHM-JAVA-NAT-EMPTY-CATCH",
    "HIGH",
)
case(
    "fn-catch-return-null",
    '''package demo.fn;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Sample {

    public String load(String id) {
        try {
            return Files.readString(Path.of("/etc", id));
        } catch (IOException ex) {
            return null;
        }
    }
}
''',
    "CHM-JAVA-NAT-CATCH-RETURN-NULL",
    "HIGH",
)
case(
    "fn-swallow-and-success",
    '''package demo.fn;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.client.RestTemplate;

public class Sample {

    private static final Logger log = LoggerFactory.getLogger(Sample.class);

    private final RestTemplate restTemplate = new RestTemplate();

    public boolean notifyPartner(String payload) {
        try {
            restTemplate.postForObject("http://partner/notify", payload, String.class);
            return true;
        } catch (Exception ex) {
            log.warn("partner notify failed", ex);
        }
        return true;
    }
}
''',
    "CHM-JAVA-NAT-SWALLOW-AND-SUCCESS",
    "HIGH",
)
case(
    "fn-unbounded-retry",
    '''package demo.fn;

import org.springframework.retry.annotation.Retryable;

public class Sample {

    @Retryable
    public String call() {
        return "ok";
    }
}
''',
    "CHM-JAVA-NAT-RETRY-AMPLIFY",
    "HIGH",
)
case(
    "fn-generic-catch",
    '''package demo.fn;

public class Sample {

    public String parse(String raw) {
        try {
            return raw.trim();
        } catch (Exception ex) {
            return raw;
        }
    }
}
''',
    "CHM-JAVA-NAT-GENERIC-CATCH",
    "LOW",
)
# ---------------------------------------------------------------------------
# resource safety
# ---------------------------------------------------------------------------
case(
    "fn-unclosed-resource",
    '''package demo.fn;

import java.io.FileInputStream;
import java.io.IOException;

public class Sample {

    public int head(String path) throws IOException {
        FileInputStream stream = new FileInputStream(path);
        return stream.read();
    }
}
''',
    "CHM-JAVA-NAT-UNCLOSED-RESOURCE",
    "HIGH",
)
case(
    "fn-executor-per-call",
    '''package demo.fn;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class Sample {

    public void run(String task) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        pool.submit(() -> task.length());
    }
}
''',
    "CHM-JAVA-NAT-EXECUTOR-PER-CALL",
    "HIGH",
)
case(
    "fn-threadpool-no-shutdown",
    '''package demo.fn;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Sample {

    @Bean
    public ExecutorService workerPool() {
        return Executors.newFixedThreadPool(4);
    }
}
''',
    "CHM-JAVA-NAT-THREADPOOL-NO-SHUTDOWN",
    "LOW",
)
# ---------------------------------------------------------------------------
# concurrency
# ---------------------------------------------------------------------------
case(
    "fn-shared-mutable",
    '''package demo.fn;

import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class Sample {

    private final Map<String, String> cache = new HashMap<>();

    public void put(String key, String value) {
        cache.put(key, value);
    }
}
''',
    "CHM-JAVA-NAT-SHARED-MUTABLE",
    "HIGH",
)
case(
    "fn-semaphore-leak",
    '''package demo.fn;

import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

@Service
public class Sample {

    private final Semaphore permits = new Semaphore(2);

    public boolean enter(String caller) throws InterruptedException {
        permits.acquire();
        return caller != null;
    }
}
''',
    "CHM-JAVA-NAT-SEMAPHORE-LEAK",
    "HIGH",
)
case(
    "fn-lock-remote-call",
    '''package demo.fn;

import org.springframework.web.client.RestTemplate;

public class Sample {

    private final Object lock = new Object();
    private final RestTemplate restTemplate = new RestTemplate();

    public String balance(String account) {
        synchronized (lock) {
            return restTemplate.getForObject("http://ledger/" + account, String.class);
        }
    }
}
''',
    "CHM-JAVA-NAT-LOCK-REMOTE-CALL",
    "HIGH",
)
case(
    "fn-double-check-no-volatile",
    '''package demo.fn;

public class Sample {

    private Holder instance;

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
    "CHM-JAVA-NAT-DOUBLE-CHECK-NO-VOLATILE",
    "HIGH",
)
case(
    "fn-no-idempotency",
    '''package demo.fn;

import org.apache.ibatis.annotations.Mapper;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Sample {

    private final RowMapper rowMapper = new RowMapperImpl();
    private final PayClient payClient = new PayClient();

    @PostMapping("/pay")
    public String pay(@RequestBody PayRequest request) {
        rowMapper.insert(request.toRow());
        payClient.transfer(request.getAccount(), request.getAmount());
        return "ok";
    }

    @Mapper
    public interface RowMapper {
        int insert(String row);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public int insert(String row) {
            return 1;
        }
    }

    public static class PayClient {
        public void transfer(String account, long amount) {
        }
    }

    public static class PayRequest {
        public String getAccount() {
            return "a";
        }

        public long getAmount() {
            return 1L;
        }

        public String toRow() {
            return "a:1";
        }
    }
}
''',
    "CHM-JAVA-NAT-NO-IDEMPOTENCY",
    "HIGH",
)
# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------
case(
    "fn-nplus1",
    '''package demo.fn;

import java.util.ArrayList;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper = new RowMapperImpl();

    public List<String> detailNames() {
        List<String> rows = mapper.selectList(null);
        List<String> out = new ArrayList<>();
        for (String row : rows) {
            out.add(mapper.selectById(row));
        }
        return out;
    }

    @Mapper
    public interface RowMapper {
        List<String> selectList(Object wrapper);

        String selectById(String id);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public List<String> selectList(Object wrapper) {
            return List.of();
        }

        @Override
        public String selectById(String id) {
            return id;
        }
    }
}
''',
    "CHM-JAVA-NAT-NPLUS1",
    "HIGH",
)
case(
    "fn-update-no-where",
    '''package demo.fn;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper = new RowMapperImpl();

    public void purge() {
        mapper.execute("UPDATE archived_rows SET purged = 1");
    }

    @Mapper
    public interface RowMapper {
        int execute(String sql);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public int execute(String sql) {
            return 1;
        }
    }
}
''',
    "CHM-JAVA-NAT-UPDATE-NO-WHERE",
    "CRITICAL",
)
case(
    "fn-delete-no-where",
    '''package demo.fn;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper = new RowMapperImpl();

    public void wipe() {
        mapper.execute("DELETE FROM archived_rows");
    }

    @Mapper
    public interface RowMapper {
        int execute(String sql);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public int execute(String sql) {
            return 1;
        }
    }
}
''',
    "CHM-JAVA-NAT-DELETE-NO-WHERE",
    "CRITICAL",
)
case(
    "fn-tx-remote-call",
    '''package demo.fn;

import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

public class Sample {

    private final RestTemplate restTemplate = new RestTemplate();

    @Transactional
    public void post(String account) {
        restTemplate.postForObject("http://ledger/post", account, String.class);
    }
}
''',
    "CHM-JAVA-NAT-TX-REMOTE-CALL",
    "HIGH",
)
case(
    "fn-select-star",
    '''package demo.fn;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper = new RowMapperImpl();

    public String all() {
        return mapper.one("SELECT * FROM rows");
    }

    @Mapper
    public interface RowMapper {
        String one(String sql);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public String one(String sql) {
            return "";
        }
    }
}
''',
    "CHM-JAVA-NAT-SELECT-STAR",
    "LOW",
)
case(
    "fn-unbounded-in",
    '''package demo.fn;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper = new RowMapperImpl();

    public String byIds() {
        return mapper.one("SELECT id FROM rows WHERE id IN (#{ids})");
    }

    @Mapper
    public interface RowMapper {
        String one(String sql);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public String one(String sql) {
            return "";
        }
    }
}
''',
    "CHM-JAVA-NAT-UNBOUNDED-IN",
    "MEDIUM",
)
case(
    "fn-dup-sql",
    '''package demo.fn;

import org.apache.ibatis.annotations.Mapper;

public class Sample {

    private final RowMapper mapper = new RowMapperImpl();

    public String one() {
        return mapper.one("SELECT name FROM tenants WHERE active = 1");
    }

    @Mapper
    public interface RowMapper {
        String one(String sql);
    }

    public static class RowMapperImpl implements RowMapper {
        @Override
        public String one(String sql) {
            return "";
        }
    }
}
''',
    "CHM-JAVA-NAT-DUP-SQL",
    "MEDIUM",
    extra={
        "src/main/java/demo/fn/OtherA.java": (
            "package demo.fn;\n\npublic class OtherA {\n"
            "    public String sql() {\n"
            '        return "SELECT name FROM tenants WHERE active = 1";\n    }\n}\n'
        ),
        "src/main/java/demo/fn/OtherB.java": (
            "package demo.fn;\n\npublic class OtherB {\n"
            "    public String sql() {\n"
            '        return "SELECT name FROM tenants WHERE active = 1";\n    }\n}\n'
        ),
    },
)
# ---------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------
case(
    "fn-on2",
    '''package demo.fn;

import java.util.ArrayList;
import java.util.List;

public class Sample {

    public List<String> overlap(List<String> left, List<String> right) {
        List<String> out = new ArrayList<>();
        for (String a : left) {
            for (String b : right) {
                if (left.contains(b)) {
                    out.add(a + b);
                }
            }
        }
        return out;
    }
}
''',
    "CHM-JAVA-NAT-ON2",
    "MEDIUM",
)
case(
    "fn-repeat-serialize",
    '''package demo.fn;

import com.alibaba.fastjson.JSON;
import java.util.HashMap;
import java.util.Map;

public class Sample {

    public Map<String, String> fanOut(Map<String, Object> payload) {
        Map<String, String> out = new HashMap<>();
        out.put("a", JSON.toJSONString(payload));
        out.put("b", JSON.toJSONString(payload));
        out.put("c", JSON.toJSONString(payload));
        return out;
    }
}
''',
    "CHM-JAVA-NAT-REPEAT-SERIALIZE",
    "MEDIUM",
)
# ---------------------------------------------------------------------------
# testability
# ---------------------------------------------------------------------------
case(
    "fn-hardcoded-time",
    '''package demo.fn;

import java.time.LocalDateTime;

public class Sample {

    public String stamp() {
        LocalDateTime a = LocalDateTime.now();
        LocalDateTime b = LocalDateTime.now();
        LocalDateTime c = LocalDateTime.now();
        return a + "/" + b + "/" + c;
    }
}
''',
    "CHM-JAVA-NAT-HARDCODED-TIME",
    "MEDIUM",
)
case(
    "fn-global-mutable-singleton",
    '''package demo.fn;

public class Sample {

    public static String currentTenant;

    public String tenant() {
        return currentTenant;
    }
}
''',
    "CHM-JAVA-NAT-GLOBAL-MUTABLE-SINGLETON",
    "MEDIUM",
)
# ---------------------------------------------------------------------------
# dead code
# ---------------------------------------------------------------------------
case(
    "fn-unused-private-method",
    '''package demo.fn;

public class Sample {

    public int total(int value) {
        return value + 1;
    }

    private String abandoned() {
        return "never called";
    }
}
''',
    "CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD",
    "MEDIUM",
)
case(
    "fn-unused-field",
    '''package demo.fn;

public class Sample {

    private String orphaned;

    public int size() {
        return 0;
    }
}
''',
    "CHM-JAVA-NAT-UNUSED-FIELD",
    "LOW",
)
case(
    "fn-commented-code",
    '''package demo.fn;

public class Sample {

    public int size() {
        return 0;
    }
    /*
    private String abandoned(String raw) {
        String text = raw.trim();
        return text.toLowerCase();
    }
    private void reset() {
        this.orphaned = null;
    }
    */
}
''',
    "CHM-JAVA-NAT-COMMENTED-CODE",
    "LOW",
)
case(
    "fn-todo-marker",
    '''package demo.fn;

public class Sample {

    // TODO: remove this before the release
    public int size() {
        return 0;
    }
}
''',
    "CHM-JAVA-NAT-TODO-MARKER",
    "LOW",
)
case(
    "fn-debug-residue",
    '''package demo.fn;

public class Sample {

    public int size() {
        System.out.println("size called");
        return 0;
    }
}
''',
    "CHM-JAVA-NAT-DEBUG-RESIDUE",
    "LOW",
)
case(
    "fn-unreachable-branch",
    '''package demo.fn;

public class Sample {

    public int size() {
        if (false) {
            return 1;
        }
        return 0;
    }
}
''',
    "CHM-JAVA-NAT-UNREACHABLE-BRANCH",
    "LOW",
)
case(
    "fn-compat-junk",
    '''package demo.fn;

public class Sample {

    public String legacyShape() {
        return "old";
    }
}
''',
    "CHM-JAVA-NAT-COMPAT-JUNK",
    "LOW",
)
case(
    "fn-unused-config-key",
    '''package demo.fn;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class Sample {

    @Value("${sample.missing-key}")
    private String missing;

    public String value() {
        return missing;
    }
}
''',
    "CHM-JAVA-NAT-UNUSED-CONFIG-KEY",
    "LOW",
    extra={"src/main/resources/application.properties": "sample.present-key=1\n"},
)
# ---------------------------------------------------------------------------
# complexity / size
# ---------------------------------------------------------------------------
case(
    "fn-deep-nesting",
    '''package demo.fn;

public class Sample {

    public int walk(int[] values) {
        int total = 0;
        for (int a : values) {
            for (int b : values) {
                for (int c : values) {
                    for (int d : values) {
                        for (int e : values) {
                            if (a + b + c + d + e > 0) {
                                total += a;
                            }
                        }
                    }
                }
            }
        }
        return total;
    }
}
''',
    "CHM-JAVA-NAT-DEEP-NESTING",
    "MEDIUM",
)
case(
    "fn-cyclomatic",
    '''package demo.fn;

public class Sample {

    public int classify(int a, int b, int c) {
        int score = 0;
        if (a > 1) { score++; }
        if (a > 2) { score++; }
        if (a > 3) { score++; }
        if (a > 4) { score++; }
        if (b > 1) { score++; }
        if (b > 2) { score++; }
        if (b > 3) { score++; }
        if (b > 4) { score++; }
        if (c > 1) { score++; }
        if (c > 2) { score++; }
        if (c > 3) { score++; }
        if (c > 4) { score++; }
        if (a + b > c) { score++; }
        if (a + c > b) { score++; }
        if (b + c > a) { score++; }
        if (a == b) { score++; }
        return score;
    }
}
''',
    "CHM-JAVA-NAT-CYCLOMATIC",
    "MEDIUM",
)
case(
    "fn-long-param-list",
    '''package demo.fn;

public class Sample {

    public String join(String a, String b, String c, String d, String e, String f) {
        return a + b + c + d + e + f;
    }
}
''',
    "CHM-JAVA-NAT-LONG-PARAM-LIST",
    "LOW",
)
case(
    "fn-large-class",
    '''package demo.fn;

public class Sample {

'''
    + "".join(f"    private String field{i};\n" for i in range(31))
    + '''
    public String first() {
        return field0;
    }
}
''',
    "CHM-JAVA-NAT-LARGE-CLASS",
    "LOW",
)
case(
    "fn-large-method",
    '''package demo.fn;

public class Sample {

    public int process(int seed) {
        int total = seed;
'''
    + "".join(
        f"        if (total > {i}) {{\n            total = total - {i};\n        }} else {{\n"
        f"            total = total + {i};\n        }}\n"
        for i in range(1, 31)
    )
    + '''
        return total;
    }
}
''',
    "CHM-JAVA-NAT-LARGE-METHOD",
    "MEDIUM",
)
# ---------------------------------------------------------------------------
# duplication
# ---------------------------------------------------------------------------
case(
    "fn-duplicate-block",
    '''package demo.fn;

import java.math.BigDecimal;
import java.util.List;

public class Sample {

    public BigDecimal computeTotal(List<Line> lines, String region) {
        BigDecimal subtotal = BigDecimal.ZERO;
        BigDecimal tax = BigDecimal.ZERO;
        for (Line line : lines) {
            BigDecimal unit = line.getUnitPrice().multiply(BigDecimal.valueOf(line.getQuantity()));
            if (line.isTaxable()) {
                tax = tax.add(unit.multiply(new BigDecimal("0.13")));
            }
            subtotal = subtotal.add(unit);
        }
        if ("EU".equals(region)) {
            subtotal = subtotal.add(new BigDecimal("4.50"));
        } else if ("APAC".equals(region)) {
            subtotal = subtotal.add(new BigDecimal("2.25"));
        } else {
            subtotal = subtotal.add(new BigDecimal("1.00"));
        }
        BigDecimal total = subtotal.add(tax);
        if (total.signum() < 0) {
            return BigDecimal.ZERO;
        }
        return total.setScale(2, java.math.RoundingMode.HALF_UP);
    }

    public static class Line {
        public BigDecimal getUnitPrice() {
            return BigDecimal.ONE;
        }

        public int getQuantity() {
            return 1;
        }

        public boolean isTaxable() {
            return true;
        }
    }
}
''',
    "CHM-JAVA-NAT-DUPLICATE-BLOCK",
    "MEDIUM",
    extra={
        "src/main/java/demo/fn/Twin.java": (
            "package demo.fn;\n\nimport java.math.BigDecimal;\nimport java.util.List;\n\n"
            "public class Twin {\n\n"
            "    public BigDecimal computeTotal(List<Sample.Line> lines, String region) {\n"
            "        BigDecimal subtotal = BigDecimal.ZERO;\n"
            "        BigDecimal tax = BigDecimal.ZERO;\n"
            "        for (Sample.Line line : lines) {\n"
            "            BigDecimal unit = line.getUnitPrice().multiply(BigDecimal.valueOf(line.getQuantity()));\n"
            "            if (line.isTaxable()) {\n"
            '                tax = tax.add(unit.multiply(new BigDecimal("0.13")));\n'
            "            }\n"
            "            subtotal = subtotal.add(unit);\n"
            "        }\n"
            '        if ("EU".equals(region)) {\n'
            '            subtotal = subtotal.add(new BigDecimal("4.50"));\n'
            '        } else if ("APAC".equals(region)) {\n'
            '            subtotal = subtotal.add(new BigDecimal("2.25"));\n'
            "        } else {\n"
            '            subtotal = subtotal.add(new BigDecimal("1.00"));\n'
            "        }\n"
            "        BigDecimal total = subtotal.add(tax);\n"
            "        if (total.signum() < 0) {\n"
            "            return BigDecimal.ZERO;\n"
            "        }\n"
            "        return total.setScale(2, java.math.RoundingMode.HALF_UP);\n"
            "    }\n}\n"
        )
    },
)
case(
    "fn-duplicate-business-rule",
    '''package demo.fn;

public class Sample {

    public boolean first(String status, boolean paid) {
        if ("ACTIVE".equals(status) && paid) {
            return true;
        }
        return false;
    }

    public boolean second(String status, boolean paid) {
        if ("ACTIVE".equals(status) && paid) {
            return true;
        }
        return false;
    }

    public boolean third(String status, boolean paid) {
        if ("ACTIVE".equals(status) && paid) {
            return true;
        }
        return false;
    }
}
''',
    "CHM-JAVA-NAT-DUPLICATE-BUSINESS-RULE",
    "MEDIUM",
)
# ---------------------------------------------------------------------------
# abstraction
# ---------------------------------------------------------------------------
case(
    "fn-single-impl-interface",
    '''package demo.fn;

public interface Sample {

    String find(String id);
}
''',
    "CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE",
    "MEDIUM",
    extra={
        "src/main/java/demo/fn/SampleImpl.java": (
            "package demo.fn;\n\npublic class SampleImpl implements Sample {\n"
            "    @Override\n    public String find(String id) {\n"
            "        return id;\n    }\n}\n"
        )
    },
)
case(
    "fn-single-call-wrapper",
    '''package demo.fn;

public class Sample {

    private final Repository repository;

    public Sample(Repository repository) {
        this.repository = repository;
    }

    public String find(String id) {
        return repository.find(id);
    }

    public void save(String id) {
        repository.save(id);
    }

    public int count() {
        return repository.count();
    }

    public static class Repository {
        public String find(String id) {
            return id;
        }

        public void save(String id) {
        }

        public int count() {
            return 0;
        }
    }
}
''',
    "CHM-JAVA-NAT-SINGLE-CALL-WRAPPER",
    "MEDIUM",
)
case(
    "fn-speculative-factory",
    '''package demo.fn;

class SampleFactory {
    String kind() {
        return "factory";
    }
}

class SampleProvider {
    String kind() {
        return "provider";
    }
}

class SampleRegistry {
    String kind() {
        return "registry";
    }
}
''',
    "CHM-JAVA-NAT-SPECULATIVE-FACTORY",
    "MEDIUM",
)
# ---------------------------------------------------------------------------
# Vue / JS
# ---------------------------------------------------------------------------
case(
    "fn-vue-unused-component",
    '''<template>
  <div class="sample">
    <span>{{ label }}</span>
  </div>
</template>

<script>
import OrphanWidget from '@/components/OrphanWidget.vue'

export default {
  name: 'Sample',
  components: { OrphanWidget },
  data() {
    return { label: 'x' }
  }
}
</script>
''',
    "CHM-JS-NAT-UNUSED-COMPONENT",
    "MEDIUM",
    filename="src/views/Sample.vue",
)
case(
    "fn-vue-unused-export",
    '''export function orphanHelper(value) {
  if (!value) {
    return ''
  }
  return value.trim()
}
''',
    "CHM-JS-NAT-UNUSED-EXPORT",
    "LOW",
    filename="src/utils/orphan.js",
)
case(
    "fn-vue-dup-computed",
    '''<template>
  <div class="sample">
    <span>{{ first }}</span>
    <span>{{ second }}</span>
  </div>
</template>

<script>
export default {
  name: 'Sample',
  data() {
    return { users: [] }
  },
  computed: {
    first() {
      const list = this.users.filter((u) => u.active)
      const sorted = list.sort((a, b) => a.name.localeCompare(b.name))
      return sorted.map((u) => u.name)
    },
    second() {
      const list = this.users.filter((u) => u.active)
      const sorted = list.sort((a, b) => a.name.localeCompare(b.name))
      return sorted.map((u) => u.name)
    }
  }
}
</script>
''',
    "CHM-JS-NAT-DUP-COMPUTED",
    "MEDIUM",
    filename="src/views/Sample.vue",
)
case(
    "fn-vue-huge-component",
    '''<template>
  <div class="sample">{{ a0 }}</div>
</template>

<script>
export default {
  name: 'Sample',
  data() {
    return {
'''
    + "".join(f"      a{i}: {i},\n" for i in range(31))
    + '''    }
  }
}
</script>
''',
    "CHM-JS-NAT-HUGE-COMPONENT",
    "LOW",
    filename="src/views/Sample.vue",
)
case(
    "fn-vue-unused-dependency",
    '''<template>
  <div class="sample">ok</div>
</template>

<script>
export default {
  name: 'Sample'
}
</script>
''',
    "CHM-JS-NAT-UNUSED-DEPENDENCY-DECL",
    "MEDIUM",
    filename="src/views/Sample.vue",
    extra={
        "package.json": '''{
  "name": "fn-sample",
  "version": "1.0.0",
  "dependencies": {
    "moment": "^2.29.4",
    "vue": "^2.7.14"
  }
}
'''
    },
    config=golden_config({"source_roots": ["."]}),
)
case(
    "fn-js-empty-catch",
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
      } catch (e) {}
      return {}
    }
  }
}
</script>
''',
    "CHM-JS-NAT-EMPTY-CATCH",
    "HIGH",
    filename="src/views/Sample.vue",
)
case(
    "fn-js-debug-residue",
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
    "CHM-JS-NAT-DEBUG-RESIDUE",
    "LOW",
    filename="src/views/Sample.vue",
)
case(
    "fn-js-todo-marker",
    '''<template>
  <div class="sample">ok</div>
</template>

<script>
export default {
  name: 'Sample'
  // TODO: split this component
}
</script>
''',
    "CHM-JS-NAT-TODO-MARKER",
    "LOW",
    filename="src/views/Sample.vue",
)
case(
    "fn-js-api-passthru",
    '''import request from '@/utils/request'

export function fetchThing(id) {
  return request({
    url: '/thing/' + id,
    method: 'get'
  })
}
''',
    "CHM-JS-NAT-API-WRAPPER-PASSTHRU",
    "LOW",
    filename="src/api/thing.js",
)


class FalseNegativeTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.results: list[tuple[str, str, str, bool, str]] = []
        for label, source, filename, rule, severity, extra, config in CASES:
            run = run_source(
                source, filename=filename, extra_files=extra, config=config
            )
            detected = rule in run.rules() or rule in run.raw_rules()
            cls.results.append((label, rule, severity, detected, filename))
        cls.stats = cls._stats()

        print("\n" + "=" * 78)
        print("FALSE-NEGATIVE SUITE (target: HIGH/CRITICAL recall >= 95%, all >= 85%)")
        print("=" * 78)
        for label, rule, severity, detected, _f in cls.results:
            print(
                f"  {'ok ' if detected else 'MISS'} {label:<32} {severity:<8} {rule}"
            )
        s = cls.stats
        print("-" * 78)
        print(
            f"  HIGH/CRITICAL recall = {s['high_rate']:.1%} "
            f"({s['high_hit']}/{s['high_total']})   (target >= {HIGH_TARGET:.0%})"
        )
        print(
            f"  all severity recall  = {s['all_rate']:.1%} "
            f"({s['all_hit']}/{s['all_total']})   (target >= {ALL_TARGET:.0%})"
        )
        print("=" * 78)
        if s["high_rate"] < HIGH_TARGET:
            print("  TARGET_MISSED: HIGH/CRITICAL recall below target")
        if s["all_rate"] < ALL_TARGET:
            print("  TARGET_MISSED: all-severity recall below target")

    @classmethod
    def _stats(cls) -> dict:
        high = [r for r in cls.results if r[2] in ("HIGH", "CRITICAL")]
        all_hit = sum(1 for r in cls.results if r[3])
        high_hit = sum(1 for r in high if r[3])
        return {
            "all_total": len(cls.results),
            "all_hit": all_hit,
            "all_rate": all_hit / len(cls.results) if cls.results else 1.0,
            "high_total": len(high),
            "high_hit": high_hit,
            "high_rate": high_hit / len(high) if high else 1.0,
        }

    def test_all_defects_are_detected(self) -> None:
        missed = [r for r in self.results if not r[3]]
        if missed:
            self.fail(
                "the following real defects were NOT detected:\n"
                + "\n".join(
                    f"    {label} -> expected {rule} ({severity}) in {fn}"
                    for label, rule, severity, _d, fn in missed
                )
            )

    def test_case_count(self) -> None:
        self.assertGreaterEqual(len(CASES), 30, "the suite must cover >= 30 defects")

    def test_targets_are_reported(self) -> None:
        s = self.stats
        print(
            f"\n  high_recall={s['high_rate']:.4f} all_recall={s['all_rate']:.4f}"
        )
        if s["high_rate"] < HIGH_TARGET or s["all_rate"] < ALL_TARGET:
            print("  TARGET_MISSED (see the numbers above)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
