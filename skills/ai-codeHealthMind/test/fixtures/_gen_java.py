"""Fixture generator: Java fixtures + the shared compile stubs.

Standard library only.  Run via ``test/fixtures/_generate.py``.

Every fixture directory is materialised from the ``FILES`` mapping below.  The
generator is kept in-tree so the fixtures are reproducible and reviewable as
code rather than as an unexplained pile of files.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# stubs: enough of Spring / MyBatis / Lombok / slf4j / micrometer / feign to
# let ``javac`` compile the fixtures without any third-party jar on the
# classpath.  They live OUTSIDE every fixture's ``src`` so the analyzers never
# see them (``source_roots`` is ``["src", "app", "lib"]``).
# --------------------------------------------------------------------------

_STUB_TYPES: dict[str, str] = {
    # --- spring stereotype / context -----------------------------------
    "org.springframework.stereotype.Component": "public @interface Component { String value() default \"\"; }",
    "org.springframework.stereotype.Service": "public @interface Service { String value() default \"\"; }",
    "org.springframework.stereotype.Repository": "public @interface Repository { String value() default \"\"; }",
    "org.springframework.stereotype.Controller": "public @interface Controller { String value() default \"\"; }",
    "org.springframework.stereotype.RestController": "public @interface RestController { String value() default \"\"; }",
    "org.springframework.context.annotation.Configuration": "public @interface Configuration { String value() default \"\"; }",
    "org.springframework.context.annotation.Bean": "public @interface Bean { String value() default \"\"; }",
    "org.springframework.context.annotation.Scope": "public @interface Scope { String value() default \"\"; }",
    "org.springframework.context.annotation.Lazy": "public @interface Lazy { boolean value() default true; }",
    "org.springframework.beans.factory.annotation.Autowired": "public @interface Autowired { boolean required() default true; }",
    "org.springframework.beans.factory.annotation.Value": "public @interface Value { String value() default \"\"; }",
    "org.springframework.beans.factory.annotation.Qualifier": "public @interface Qualifier { String value() default \"\"; }",
    "org.springframework.context.event.EventListener": "public @interface EventListener { String condition() default \"\"; }",
    "org.springframework.scheduling.annotation.Scheduled": "public @interface Scheduled { String cron() default \"\"; long fixedDelay() default -1L; long fixedRate() default -1L; }",
    "org.springframework.scheduling.annotation.Async": "public @interface Async { String value() default \"\"; }",
    "org.springframework.transaction.annotation.Transactional": "public @interface Transactional { String value() default \"\"; boolean readOnly() default false; }",
    "org.springframework.retry.annotation.Retryable": "public @interface Retryable { int maxAttempts() default 3; String value() default \"\"; }",
    "org.springframework.retry.annotation.Backoff": "public @interface Backoff { long delay() default 0L; }",
    "org.springframework.retry.annotation.CircuitBreaker": "public @interface CircuitBreaker { int maxAttempts() default 3; }",
    "org.springframework.web.bind.annotation.RestControllerAdvice": "public @interface RestControllerAdvice { String value() default \"\"; }",
    "org.springframework.web.bind.annotation.RequestMapping": "public @interface RequestMapping { String[] value() default {}; String[] path() default {}; String method() default \"GET\"; }",
    "org.springframework.web.bind.annotation.PostMapping": "public @interface PostMapping { String[] value() default {}; String[] path() default {}; }",
    "org.springframework.web.bind.annotation.GetMapping": "public @interface GetMapping { String[] value() default {}; String[] path() default {}; }",
    "org.springframework.web.bind.annotation.PutMapping": "public @interface PutMapping { String[] value() default {}; }",
    "org.springframework.web.bind.annotation.RequestBody": "public @interface RequestBody { boolean required() default true; }",
    "org.springframework.web.bind.annotation.PathVariable": "public @interface PathVariable { String value() default \"\"; }",
    "org.springframework.web.bind.annotation.RequestParam": "public @interface RequestParam { String value() default \"\"; }",
    "org.springframework.cloud.openfeign.FeignClient": "public @interface FeignClient { String name() default \"\"; String url() default \"\"; }",
    "org.springframework.kafka.annotation.KafkaListener": "public @interface KafkaListener { String[] topics() default {}; String id() default \"\"; }",
    "org.springframework.amqp.rabbit.annotation.RabbitListener": "public @interface RabbitListener { String[] queues() default {}; }",
    "javax.annotation.PostConstruct": "public @interface PostConstruct { }",
    "javax.annotation.PreDestroy": "public @interface PreDestroy { }",
    "javax.annotation.Resource": "public @interface Resource { String name() default \"\"; }",
    # --- persistence ---------------------------------------------------
    "org.apache.ibatis.annotations.Mapper": "public @interface Mapper { String value() default \"\"; }",
    "org.apache.ibatis.annotations.Select": "public @interface Select { String[] value() default {}; }",
    # --- lombok --------------------------------------------------------
    "lombok.Getter": "public @interface Getter { }",
    "lombok.Setter": "public @interface Setter { }",
    "lombok.Data": "public @interface Data { }",
    # --- misc ----------------------------------------------------------
    "com.fasterxml.jackson.annotation.JsonProperty": "public @interface JsonProperty { String value() default \"\"; }",
    "org.springframework.data.redis.core.RedisTemplate": "public class RedisTemplate<K, V> { public void opsForValue() { } }",
}

# interfaces / classes with a small but real body
_STUB_BODIES: dict[str, str] = {
    "org.slf4j.Logger": (
        "public interface Logger {"
        " void info(String m, Object... a); void warn(String m, Object... a);"
        " void error(String m, Object... a); void debug(String m, Object... a); }"
    ),
    "org.slf4j.LoggerFactory": (
        "public final class LoggerFactory { private LoggerFactory() { }"
        " public static Logger getLogger(Class<?> c) { return new Logger() {"
        " public void info(String m, Object... a) { } public void warn(String m, Object... a) { }"
        " public void error(String m, Object... a) { } public void debug(String m, Object... a) { } }; } }"
    ),
    "io.micrometer.core.instrument.Counter": (
        "public interface Counter { void increment(); double count(); }"
    ),
    "io.micrometer.core.instrument.MeterRegistry": (
        "public interface MeterRegistry { Counter counter(String name, String... tags); }"
    ),
    "org.springframework.jdbc.core.JdbcTemplate": (
        "public class JdbcTemplate { public int update(String sql) { return 0; }"
        " public java.util.List<java.util.Map<String, Object>> queryForList(String sql) { return java.util.List.of(); } }"
    ),
    "org.springframework.web.client.RestTemplate": (
        "public class RestTemplate {"
        " public <T> T getForObject(String url, Class<T> type, Object... vars) { return null; }"
        " public <T> T postForObject(String url, Object body, Class<T> type, Object... vars) { return null; }"
        " public <T> T exchange(String url, Object method, Object entity, Class<T> type) { return null; } }"
    ),
    "com.baomidou.mybatisplus.core.mapper.BaseMapper": (
        "public interface BaseMapper<T> { T selectById(java.io.Serializable id);"
        " java.util.List<T> selectBatchIds(java.util.Collection<? extends java.io.Serializable> ids);"
        " java.util.List<T> selectList(Object wrapper); int insert(T entity); int updateById(T entity);"
        " int deleteById(java.io.Serializable id); }"
    ),
    "com.baomidou.mybatisplus.core.conditions.query.QueryWrapper": (
        "public class QueryWrapper<T> { public QueryWrapper<T> eq(String c, Object v) { return this; } }"
    ),
    "com.alibaba.fastjson.JSON": (
        "public final class JSON { private JSON() { }"
        " public static String toJSONString(Object o) { return \"{}\"; }"
        " public static byte[] toJSONBytes(Object o) { return new byte[0]; } }"
    ),
    "com.fasterxml.jackson.databind.ObjectMapper": (
        "public class ObjectMapper { public String writeValueAsString(Object o) throws Exception { return \"{}\"; } }"
    ),
    "com.acme.pay.PaymentClient": (
        "public class PaymentClient { public String charge(String orderNo, long amountCents) { return \"tx\"; }"
        " public boolean refund(String transactionId, long amountCents) { return true; } }"
    ),
    "com.acme.sms.SmsGateway": (
        "public class SmsGateway { public void send(String to, String body) throws SmsException { } }"
    ),
    "com.acme.sms.SmsException": (
        "public class SmsException extends Exception { public SmsException(String m) { super(m); } }"
    ),
}


def stub_files() -> dict[str, str]:
    """Relative path -> content for the shared compile stubs."""
    out: dict[str, str] = {}
    for fqn, body in {**_STUB_TYPES, **_STUB_BODIES}.items():
        pkg, _, name = fqn.rpartition(".")
        out[f"_stubs/src/{pkg.replace('.', '/')}/{name}.java"] = f"package {pkg};\n\n{body}\n"
    return out


# --------------------------------------------------------------------------
# Java fixtures
# --------------------------------------------------------------------------

_JC = "src/main/java/demo/clean"
_JD = "src/main/java/demo/dead"
_JU = "src/main/java/demo/dup"
_JO = "src/main/java/demo/over"
_JE = "src/main/java/demo/err"
_EC = "src/main/java/demo/conc"
_JP = "src/main/java/demo/perf"
_JDB = "src/main/java/demo/db"
_JR = "src/main/java/demo/refl"
_JM = "src/main/java/demo/mixed"

JAVA_FILES: dict[str, str] = {
    # ======================================================================
    # java-clean -- a healthy change set.  Zero MEDIUM+ findings is the
    # false-positive baseline (see the fixture README).
    # ======================================================================
    f"{_JC}/config/ClockConfig.java": '''package demo.clean.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfig {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
''',
    f"{_JC}/io/ReportReader.java": '''package demo.clean.io;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class ReportReader {

    public List<String> readLines(String path) throws IOException {
        List<String> lines = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(path), StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            while (line != null) {
                if (!line.isBlank()) {
                    lines.add(line.trim());
                }
                line = reader.readLine();
            }
        }
        return lines;
    }
}
''',
    f"{_JC}/cache/SessionRegistry.java": '''package demo.clean.cache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class SessionRegistry {

    private final Map<String, Long> lastSeen = new ConcurrentHashMap<>();

    public void touch(String sessionId, long epochMillis) {
        lastSeen.put(sessionId, epochMillis);
    }

    public int size() {
        return lastSeen.size();
    }

    public void forget(String sessionId) {
        lastSeen.remove(sessionId);
    }
}
''',
    f"{_JC}/order/Order.java": '''package demo.clean.order;

public class Order {

    private final long id;
    private final long amount;
    private final String status;

    public Order(long id, long amount, String status) {
        this.id = id;
        this.amount = amount;
        this.status = status;
    }

    public long getId() {
        return id;
    }

    public long getAmount() {
        return amount;
    }

    public String getStatus() {
        return status;
    }
}
''',
    f"{_JC}/order/OrderView.java": '''package demo.clean.order;

public class OrderView {

    private final long id;
    private final long amount;
    private final String status;

    public OrderView(long id, long amount, String status) {
        this.id = id;
        this.amount = amount;
        this.status = status;
    }

    public long getId() {
        return id;
    }

    public long getAmount() {
        return amount;
    }

    public String getStatus() {
        return status;
    }
}
''',
    f"{_JC}/order/OrderMapper.java": '''package demo.clean.order;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface OrderMapper {

    List<Order> selectBatchIds(List<Long> ids);

    Order selectById(Long id);
}
''',
    f"{_JC}/order/OrderService.java": '''package demo.clean.order;

import java.time.Clock;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderMapper orderMapper;
    private final Clock clock;

    public OrderService(OrderMapper orderMapper, Clock clock) {
        this.orderMapper = orderMapper;
        this.clock = clock;
    }

    public List<OrderView> load(List<Long> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }
        List<Order> orders = orderMapper.selectBatchIds(ids);
        return orders.stream().map(this::toView).toList();
    }

    public long secondsSince(long epochMillis) {
        return (clock.millis() - epochMillis) / 1000L;
    }

    private OrderView toView(Order order) {
        return new OrderView(order.getId(), order.getAmount(), order.getStatus());
    }
}
''',
    "src/main/resources/mapper/OrderMapper.xml": '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="demo.clean.order.OrderMapper">
    <select id="selectById" resultType="demo.clean.order.Order">
        SELECT id, amount, status FROM orders WHERE id = #{id}
    </select>
    <select id="selectBatchIds" resultType="demo.clean.order.Order">
        SELECT id, amount, status FROM orders WHERE id IN
        <foreach collection="ids" item="item" open="(" separator="," close=")">#{item}</foreach>
    </select>
</mapper>
''',
    f"{_JC}/pricing/PricingStrategy.java": '''package demo.clean.pricing;

import java.math.BigDecimal;

public interface PricingStrategy {

    String name();

    BigDecimal price(BigDecimal base);
}
''',
    f"{_JC}/pricing/RetailPricing.java": '''package demo.clean.pricing;

import java.math.BigDecimal;

public class RetailPricing implements PricingStrategy {

    @Override
    public String name() {
        return "retail";
    }

    @Override
    public BigDecimal price(BigDecimal base) {
        return base;
    }
}
''',
    f"{_JC}/pricing/WholesalePricing.java": '''package demo.clean.pricing;

import java.math.BigDecimal;
import java.math.RoundingMode;

public class WholesalePricing implements PricingStrategy {

    @Override
    public String name() {
        return "wholesale";
    }

    @Override
    public BigDecimal price(BigDecimal base) {
        return base.multiply(new BigDecimal("0.82")).setScale(2, RoundingMode.HALF_UP);
    }
}
''',
    f"{_JC}/pricing/VipPricing.java": '''package demo.clean.pricing;

import java.math.BigDecimal;

public class VipPricing implements PricingStrategy {

    @Override
    public String name() {
        return "vip";
    }

    @Override
    public BigDecimal price(BigDecimal base) {
        BigDecimal discounted = base.subtract(new BigDecimal("15.00"));
        return discounted.signum() < 0 ? BigDecimal.ZERO : discounted;
    }
}
''',
    f"{_JC}/sdk/PaymentSdkAdapter.java": '''package demo.clean.sdk;

import com.acme.pay.PaymentClient;
import org.springframework.stereotype.Component;

@Component
public class PaymentSdkAdapter {

    private final PaymentClient client;

    public PaymentSdkAdapter(PaymentClient client) {
        this.client = client;
    }

    public String charge(String orderNo, long amountCents) {
        return client.charge(orderNo, amountCents);
    }

    public boolean refund(String transactionId, long amountCents) {
        return client.refund(transactionId, amountCents);
    }
}
''',
    f"{_JC}/job/NightlyJob.java": '''package demo.clean.job;

import demo.clean.io.ReportReader;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class NightlyJob {

    private static final Logger log = LoggerFactory.getLogger(NightlyJob.class);

    private final ReportReader reportReader;
    private final Counter failureCounter;

    public NightlyJob(ReportReader reportReader, MeterRegistry registry) {
        this.reportReader = reportReader;
        this.failureCounter = registry.counter("nightly.job.failure");
    }

    @Scheduled(cron = "0 0 2 * * *")
    public void run() {
        try {
            List<String> lines = reportReader.readLines("/var/reports/daily.csv");
            log.info("loaded {} lines", lines.size());
        } catch (IOException ex) {
            failureCounter.increment();
            log.warn("nightly report unavailable, will retry tomorrow", ex);
        }
    }
}
''',
    f"{_JC}/plugin/PluginLoader.java": '''package demo.clean.plugin;

import java.lang.reflect.Method;

public class PluginLoader {

    public String load(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("export");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }
}
''',
    f"{_JC}/plugin/ExporterPlugin.java": '''package demo.clean.plugin;

public class ExporterPlugin {

    private String export() {
        return "exported";
    }
}
''',
    # ======================================================================
    # java-dead-code
    # ======================================================================
    f"{_JD}/DeadCodeShowcase.java": '''package demo.dead;

import java.util.List;

public class DeadCodeShowcase {

    private String scratchBuffer;

    public int total(List<Integer> values) {
        int sum = 0;
        for (Integer value : values) {
            sum += value;
        }
        System.out.println("total=" + sum);
        return sum;
    }

    private String computeStaleTotal(List<Integer> values) {
        StringBuilder builder = new StringBuilder();
        for (Integer value : values) {
            builder.append(value).append(',');
        }
        return builder.toString();
    }

    // TODO: delete the whole block below once the migration is finished
    /*
    private String oldFormat(Integer value) {
        String text = String.valueOf(value);
        return text.trim();
    }
    private void oldReset() {
        scratchBuffer = null;
    }
    */
}
''',
    f"{_JD}/ScheduledTasks.java": '''package demo.dead;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledTasks {

    private static final Logger log = LoggerFactory.getLogger(ScheduledTasks.class);

    @Scheduled(cron = "0 0/5 * * * *")
    private void refreshIndex() {
        log.info("refreshing the search index");
    }

    @KafkaListener(topics = "orders")
    private void onOrderCreated(String payload) {
        log.info("order created: {}", payload);
    }
}
''',
    f"{_JD}/SpringComponent.java": '''package demo.dead;

import org.springframework.stereotype.Component;

@Component
public class SpringComponent {

    public int scale(int value) {
        return multiply(value);
    }

    private int multiply(int value) {
        return value * 3;
    }
}
''',
    f"{_JD}/MapperSupport.java": '''package demo.dead;

import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class MapperSupport {

    private List<String> selectByStatus(String status) {
        return List.of();
    }
}
''',
    f"{_JD}/DeadMapper.java": '''package demo.dead;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface DeadMapper {

    List<String> selectByStatus(String status);
}
''',
    "src/main/resources/mapper/DeadMapper.xml": '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="demo.dead.DeadMapper">
    <select id="selectByStatus" resultType="java.lang.String">
        SELECT name FROM dead_rows WHERE status = #{status}
    </select>
</mapper>
''',
    f"{_JD}/ReflectiveTask.java": '''package demo.dead;

public class ReflectiveTask {

    private String invokeTask() {
        return "done";
    }
}
''',
    f"{_JD}/TaskBootstrap.java": '''package demo.dead;

import java.lang.reflect.Method;

public class TaskBootstrap {

    public String boot(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("invokeTask");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }
}
''',
    # ======================================================================
    # java-duplicate
    # ======================================================================
    f"{_JU}/InvoicePricer.java": '''package demo.dup;

import java.math.BigDecimal;
import java.util.List;

public class InvoicePricer {

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
}
''',
    f"{_JU}/SubscriptionPricer.java": '''package demo.dup;

import java.math.BigDecimal;
import java.util.List;

public class SubscriptionPricer {

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
}
''',
    f"{_JU}/Line.java": '''package demo.dup;

import java.math.BigDecimal;

public class Line {

    private final BigDecimal unitPrice;
    private final int quantity;
    private final boolean taxable;

    public Line(BigDecimal unitPrice, int quantity, boolean taxable) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
        this.taxable = taxable;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public boolean isTaxable() {
        return taxable;
    }
}
''',
    f"{_JU}/RefundCalculator.java": '''package demo.dup;

import java.math.BigDecimal;

public class RefundCalculator {

    public BigDecimal refundFor(String reasonCode, BigDecimal paid, int daysHeld) {
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
}
''',
    f"{_JU}/CouponCalculator.java": '''package demo.dup;

import java.math.BigDecimal;
import java.util.List;

public class CouponCalculator {

    public BigDecimal couponValue(List<String> codes, BigDecimal paid) {
        if (codes == null || codes.isEmpty()) {
            return BigDecimal.ZERO;
        }
        BigDecimal best = codes.stream()
                .map(code -> BigDecimal.valueOf(code.length()))
                .reduce(BigDecimal.ZERO, BigDecimal::max);
        BigDecimal capped = best.min(paid);
        return capped.max(BigDecimal.ZERO);
    }
}
''',
    f"{_JU}/NullCheckA.java": '''package demo.dup;

public class NullCheckA {

    public String label(String value) {
        if (value == null) {
            return "unknown";
        }
        return value;
    }
}
''',
    f"{_JU}/NullCheckB.java": '''package demo.dup;

public class NullCheckB {

    public String title(String value) {
        if (value == null) {
            return "unknown";
        }
        return value;
    }
}
''',
    # ======================================================================
    # java-overengineering
    # ======================================================================
    f"{_JO}/OrderGateway.java": '''package demo.over;

public interface OrderGateway {

    Order find(String id);

    void save(Order order);
}
''',
    f"{_JO}/OrderGatewayImpl.java": '''package demo.over;

import java.util.HashMap;
import java.util.Map;

public class OrderGatewayImpl implements OrderGateway {

    private final Map<String, Order> storage = new HashMap<>();

    @Override
    public Order find(String id) {
        return storage.get(id);
    }

    @Override
    public void save(Order order) {
        storage.put(order.getId(), order);
    }
}
''',
    f"{_JO}/Order.java": '''package demo.over;

public class Order {

    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String getId() {
        return id;
    }
}
''',
    f"{_JO}/ReportRepository.java": '''package demo.over;

public class ReportRepository {

    public Report find(String id) {
        return new Report(id);
    }

    public void save(Report report) {
        report.touch();
    }

    public int count() {
        return 0;
    }
}
''',
    f"{_JO}/Report.java": '''package demo.over;

public class Report {

    private final String id;

    public Report(String id) {
        this.id = id;
    }

    public void touch() {
    }

    public String getId() {
        return id;
    }
}
''',
    f"{_JO}/ReportFacade.java": '''package demo.over;

public class ReportFacade {

    private final ReportRepository repository;

    public ReportFacade(ReportRepository repository) {
        this.repository = repository;
    }

    public Report find(String id) {
        return repository.find(id);
    }

    public void save(Report report) {
        repository.save(report);
    }

    public int count() {
        return repository.count();
    }
}
''',
    f"{_JO}/PaymentAbstractions.java": '''package demo.over;

class PaymentFactory {

    String kind() {
        return "factory";
    }
}

class PaymentProvider {

    String kind() {
        return "provider";
    }
}

class PaymentRegistry {

    String kind() {
        return "registry";
    }
}
''',
    f"{_JO}/InventoryClient.java": '''package demo.over;

import java.util.List;
import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(name = "inventory")
public interface InventoryClient {

    List<String> available(String sku);
}
''',
    f"{_JO}/InventoryClientImpl.java": '''package demo.over;

import java.util.List;

public class InventoryClientImpl implements InventoryClient {

    @Override
    public List<String> available(String sku) {
        return List.of();
    }
}
''',
    f"{_JO}/SmsGateway.java": '''package demo.over;

public class SmsGateway {

    public void deliver(String to, String body) throws SmsFailure {
        if (to == null || to.isBlank()) {
            throw new SmsFailure("missing destination");
        }
    }
}
''',
    f"{_JO}/SmsFailure.java": '''package demo.over;

public class SmsFailure extends Exception {

    public SmsFailure(String message) {
        super(message);
    }
}
''',
    f"{_JO}/NotificationSender.java": '''package demo.over;

public class NotificationSender {

    private final SmsGateway gateway;

    public NotificationSender(SmsGateway gateway) {
        this.gateway = gateway;
    }

    public void send(String to, String body) {
        try {
            gateway.deliver(to, body);
        } catch (SmsFailure ex) {
            throw new IllegalStateException("sms delivery failed for " + to, ex);
        }
    }

    public void resend(String to, String body) {
        try {
            gateway.deliver(to, body);
        } catch (SmsFailure ex) {
            throw new IllegalStateException("sms retry failed for " + to, ex);
        }
    }
}
''',
    f"{_JO}/ChannelRouter.java": '''package demo.over;

public interface ChannelRouter {

    String route(String channel);
}
''',
    f"{_JO}/SmsRouter.java": '''package demo.over;

public class SmsRouter implements ChannelRouter {

    @Override
    public String route(String channel) {
        return "sms:" + channel;
    }
}
''',
    f"{_JO}/MailRouter.java": '''package demo.over;

public class MailRouter implements ChannelRouter {

    @Override
    public String route(String channel) {
        return "mail:" + channel;
    }
}
''',
    f"{_JO}/PushRouter.java": '''package demo.over;

public class PushRouter implements ChannelRouter {

    @Override
    public String route(String channel) {
        return "push:" + channel;
    }
}
''',
    # ======================================================================
    # java-errors
    # ======================================================================
    f"{_JE}/SilentFailures.java": '''package demo.err;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SilentFailures {

    private static final Logger log = LoggerFactory.getLogger(SilentFailures.class);

    public String readConfig(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException ex) {
        }
        return "";
    }

    public String loadTenant(String tenantId) {
        try {
            return Files.readString(Path.of("/etc/tenants", tenantId));
        } catch (IOException ex) {
            return null;
        }
    }
}
''',
    f"{_JE}/Response.java": '''package demo.err;

public class Response<T> {

    private final T data;

    private Response(T data) {
        this.data = data;
    }

    public static <T> Response<T> success(T data) {
        return new Response<>(data);
    }

    public static <T> Response<T> failure(String message) {
        return new Response<>(null);
    }

    public T getData() {
        return data;
    }
}
''',
    f"{_JE}/InventorySync.java": '''package demo.err;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.client.RestTemplate;

public class InventorySync {

    private static final Logger log = LoggerFactory.getLogger(InventorySync.class);

    private final RestTemplate restTemplate;
    private final String endpoint;

    public InventorySync(RestTemplate restTemplate, String endpoint) {
        this.restTemplate = restTemplate;
        this.endpoint = endpoint;
    }

    public Response<String> sync(String sku) {
        try {
            String body = restTemplate.getForObject(endpoint + sku, String.class);
            return Response.success(body);
        } catch (RuntimeException ex) {
            log.error("inventory sync failed for {}", sku, ex);
        }
        return Response.success("cached");
    }
}
''',
    f"{_JE}/DegradeWithMetric.java": '''package demo.err;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class DegradeWithMetric {

    private static final Logger log = LoggerFactory.getLogger(DegradeWithMetric.class);

    private final Counter degradedCounter;

    public DegradeWithMetric(MeterRegistry registry) {
        this.degradedCounter = registry.counter("feature.flag.fallback");
    }

    public String flagValue(Path path) {
        try {
            return Files.readString(path).trim();
        } catch (IOException ex) {
            degradedCounter.increment();
            log.warn("flag file unavailable, using the safe default", ex);
            return "off";
        }
    }
}
''',
    f"{_JE}/OptionalLoader.java": '''package demo.err;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

public class OptionalLoader {

    public Optional<String> load(Path path) {
        try {
            return Optional.of(Files.readString(path));
        } catch (IOException ex) {
            return Optional.empty();
        }
    }
}
''',
    f"{_JE}/AuditController.java": '''package demo.err;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AuditController {

    private static final Logger log = LoggerFactory.getLogger(AuditController.class);

    public Response<String> audit(String id) {
        try {
            return Response.success(id);
        } catch (RuntimeException ex) {
            log.error("audit failed for {}", id, ex);
            return Response.failure("audit unavailable");
        }
    }
}
''',
    # ======================================================================
    # java-concurrency
    # ======================================================================
    f"{_EC}/SessionCache.java": '''package demo.conc;

import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class SessionCache {

    private final Map<String, String> cache = new HashMap<>();

    public String get(String key) {
        return cache.get(key);
    }

    public void put(String key, String value) {
        cache.put(key, value);
    }
}
''',
    f"{_EC}/PermitGate.java": '''package demo.conc;

import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

@Service
public class PermitGate {

    private final Semaphore permits = new Semaphore(4);

    public boolean enter(String caller) throws InterruptedException {
        permits.acquire();
        return caller != null;
    }
}
''',
    f"{_EC}/LedgerService.java": '''package demo.conc;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LedgerService {

    private final Object lock = new Object();
    private final RestTemplate restTemplate;
    private final String endpoint;

    public LedgerService(RestTemplate restTemplate, String endpoint) {
        this.restTemplate = restTemplate;
        this.endpoint = endpoint;
    }

    public String balance(String account) {
        synchronized (lock) {
            return restTemplate.getForObject(endpoint + account, String.class);
        }
    }
}
''',
    f"{_EC}/LazyConfig.java": '''package demo.conc;

public class LazyConfig {

    private Config instance;

    public Config get() {
        if (instance == null) {
            synchronized (LazyConfig.class) {
                if (instance == null) {
                    instance = new Config();
                }
            }
        }
        return instance;
    }
}
''',
    f"{_EC}/Config.java": '''package demo.conc;

public class Config {

    private final String name;

    public Config() {
        this.name = "default";
    }

    public String getName() {
        return name;
    }
}
''',
    f"{_EC}/PayController.java": '''package demo.conc;

import org.apache.ibatis.annotations.Mapper;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PayController {

    private final PayMapper payMapper;
    private final PayClient payClient;

    public PayController(PayMapper payMapper, PayClient payClient) {
        this.payMapper = payMapper;
        this.payClient = payClient;
    }

    @PostMapping("/pay")
    public String pay(@RequestBody PayRequest request) {
        payMapper.insert(request.toRow());
        payClient.transfer(request.getAccount(), request.getAmount());
        return "ok";
    }

    @Mapper
    public interface PayMapper {

        int insert(String row);
    }
}
''',
    f"{_EC}/PayRequest.java": '''package demo.conc;

public class PayRequest {

    private final String account;
    private final long amount;

    public PayRequest(String account, long amount) {
        this.account = account;
        this.amount = amount;
    }

    public String getAccount() {
        return account;
    }

    public long getAmount() {
        return amount;
    }

    public String toRow() {
        return account + ":" + amount;
    }
}
''',
    f"{_EC}/PayClient.java": '''package demo.conc;

public class PayClient {

    public void transfer(String account, long amount) {
    }
}
''',
    f"{_EC}/ConcurrentSessionCache.java": '''package demo.conc;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class ConcurrentSessionCache {

    private final Map<String, String> cache = new ConcurrentHashMap<>();

    public void put(String key, String value) {
        cache.put(key, value);
    }
}
''',
    f"{_EC}/SafePermitGate.java": '''package demo.conc;

import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

@Service
public class SafePermitGate {

    private final Semaphore permits = new Semaphore(4);

    public boolean enter(String caller) throws InterruptedException {
        permits.acquire();
        try {
            return caller != null;
        } finally {
            permits.release();
        }
    }
}
''',
    f"{_EC}/PrototypeScratch.java": '''package demo.conc;

import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class PrototypeScratch {

    private final Map<String, String> scratch = new HashMap<>();

    public void note(String key, String value) {
        scratch.put(key, value);
    }
}
''',
    # ======================================================================
    # java-performance
    # ======================================================================
    f"{_JP}/Intersection.java": '''package demo.perf;

import java.util.ArrayList;
import java.util.List;

public class Intersection {

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
    f"{_JP}/PayloadBroadcaster.java": '''package demo.perf;

import com.alibaba.fastjson.JSON;
import java.util.HashMap;
import java.util.Map;

public class PayloadBroadcaster {

    public Map<String, String> fanOut(Map<String, Object> payload, String[] topics) {
        Map<String, String> out = new HashMap<>();
        String first = JSON.toJSONString(payload);
        out.put(topics[0], first);
        out.put(topics[1], JSON.toJSONString(payload));
        out.put(topics[2], JSON.toJSONString(payload));
        out.put(topics[3], JSON.toJSONString(payload));
        out.put(topics[4], JSON.toJSONString(payload));
        return out;
    }
}
''',
    f"{_JP}/HashLookup.java": '''package demo.perf;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class HashLookup {

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
    f"{_JP}/SmallLiteralScan.java": '''package demo.perf;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class SmallLiteralScan {

    public List<String> pick(List<String> values) {
        List<String> allowed = Arrays.asList("new", "open", "closed");
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
    f"{_JP}/SequenceIssuer.java": '''package demo.perf;

public class SequenceIssuer {

    public String next(String prefix) {
        long now = System.currentTimeMillis();
        return prefix + "-" + now;
    }
}
''',
    # ======================================================================
    # java-db
    # ======================================================================
    f"{_JDB}/OrderQueryService.java": '''package demo.db;

import java.util.ArrayList;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final OrderMapper orderMapper;
    private final DetailMapper detailMapper;

    public OrderQueryService(OrderMapper orderMapper, DetailMapper detailMapper) {
        this.orderMapper = orderMapper;
        this.detailMapper = detailMapper;
    }

    public List<String> detailNames() {
        List<String> orders = orderMapper.selectList(null);
        List<String> out = new ArrayList<>();
        for (String order : orders) {
            String detail = detailMapper.selectById(order);
            out.add(detail);
        }
        return out;
    }

    @Mapper
    public interface OrderMapper {

        List<String> selectList(Object wrapper);
    }

    @Mapper
    public interface DetailMapper {

        String selectById(String id);
    }
}
''',
    f"{_JDB}/BulkMaintenance.java": '''package demo.db;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class BulkMaintenance {

    private final TableMapper tableMapper;

    public BulkMaintenance(TableMapper tableMapper) {
        this.tableMapper = tableMapper;
    }

    public void purgeExpired(String reason) {
        String statement = "UPDATE archived_rows SET purged = 1";
        tableMapper.execute(statement);
    }

    public void wipe() {
        String statement = "DELETE FROM archived_rows";
        tableMapper.execute(statement);
    }

    @Mapper
    public interface TableMapper {

        int execute(String sql);

        List<String> selectBatchIds(List<String> ids);
    }
}
''',
    f"{_JDB}/LedgerTxService.java": '''package demo.db;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

@Service
public class LedgerTxService {

    private final RestTemplate restTemplate;
    private final String endpoint;

    public LedgerTxService(RestTemplate restTemplate, String endpoint) {
        this.restTemplate = restTemplate;
        this.endpoint = endpoint;
    }

    @Transactional
    public void post(String account) {
        restTemplate.postForObject(endpoint, account, String.class);
    }
}
''',
    f"{_JDB}/SafeQueries.java": '''package demo.db;

import java.util.ArrayList;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class SafeQueries {

    private final SafeMapper safeMapper;

    public SafeQueries(SafeMapper safeMapper) {
        this.safeMapper = safeMapper;
    }

    public void rename(String id) {
        String statement = "UPDATE archived_rows SET label = 'x' WHERE id = #{id}";
        safeMapper.execute(statement);
    }

    public String firstPage() {
        String statement = "SELECT * FROM archived_rows LIMIT 100";
        return safeMapper.one(statement);
    }

    public List<String> prefetch(List<List<String>> chunks) {
        List<String> out = new ArrayList<>();
        for (List<String> chunk : chunks) {
            List<String> batch = safeMapper.selectList(chunk);
            out.addAll(batch);
        }
        return out;
    }

    @Mapper
    public interface SafeMapper {

        int execute(String sql);

        String one(String sql);

        List<String> selectList(List<String> ids);
    }
}
''',
    # ======================================================================
    # java-reflection
    # ======================================================================
    f"{_JR}/spi/Plugin.java": '''package demo.refl.spi;

public interface Plugin {

    String id();

    String render(String input);
}
''',
    f"{_JR}/spi/JsonPlugin.java": '''package demo.refl.spi;

public class JsonPlugin implements Plugin {

    @Override
    public String id() {
        return "json";
    }

    @Override
    public String render(String input) {
        return "{\\"value\\":\\"" + escape(input) + "\\"}";
    }

    private String escape(String raw) {
        return raw.replace("\\"", "\\\\\\"");
    }
}
''',
    f"{_JR}/spi/XmlPlugin.java": '''package demo.refl.spi;

public class XmlPlugin implements Plugin {

    @Override
    public String id() {
        return "xml";
    }

    @Override
    public String render(String input) {
        return "<value>" + input + "</value>";
    }
}
''',
    "src/main/resources/META-INF/services/demo.refl.spi.Plugin": '''demo.refl.spi.JsonPlugin
demo.refl.spi.XmlPlugin
''',
    f"{_JR}/PluginBootstrap.java": '''package demo.refl;

import java.util.ServiceLoader;
import demo.refl.spi.Plugin;

public class PluginBootstrap {

    public int count() {
        int total = 0;
        for (Plugin plugin : ServiceLoader.load(Plugin.class)) {
            total++;
        }
        return total;
    }
}
''',
    f"{_JR}/Exporter.java": '''package demo.refl;

public class Exporter {

    private String render() {
        return "rendered";
    }
}
''',
    f"{_JR}/ExporterFactory.java": '''package demo.refl;

import java.lang.reflect.Method;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExporterFactory {

    @Bean
    public Exporter exporter() {
        return new Exporter();
    }

    public String invoke(String className) throws ReflectiveOperationException {
        Class<?> type = Class.forName(className);
        Method method = type.getDeclaredMethod("render");
        Object instance = type.getDeclaredConstructor().newInstance();
        return String.valueOf(method.invoke(instance));
    }
}
''',
    # ======================================================================
    # mixed-project (Java half)
    # ======================================================================
    f"{_JM}/api/HealthEndpoint.java": '''package demo.mixed.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthEndpoint {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
''',
    f"{_JM}/api/OrderFacade.java": '''package demo.mixed.api;

public interface OrderFacade {

    String status(String orderId);
}
''',
    f"{_JM}/api/OrderFacadeImpl.java": '''package demo.mixed.api;

public class OrderFacadeImpl implements OrderFacade {

    @Override
    public String status(String orderId) {
        return "OPEN";
    }
}
''',
    f"{_JM}/report/ReportGateway.java": '''package demo.mixed.report;

import java.util.List;

public interface ReportGateway {

    List<String> rows(String tenant);

    String export(String tenant);
}
''',
    f"{_JM}/report/ReportGatewayImpl.java": '''package demo.mixed.report;

import java.util.ArrayList;
import java.util.List;

public class ReportGatewayImpl implements ReportGateway {

    @Override
    public List<String> rows(String tenant) {
        return new ArrayList<>();
    }

    @Override
    public String export(String tenant) {
        return "csv:" + tenant;
    }
}
''',
}

__all__ = ["JAVA_FILES", "stub_files"]
