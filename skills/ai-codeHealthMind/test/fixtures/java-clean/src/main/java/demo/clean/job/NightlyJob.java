package demo.clean.job;

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
