package demo.err;

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
