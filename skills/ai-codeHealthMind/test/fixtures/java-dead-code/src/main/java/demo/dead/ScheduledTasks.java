package demo.dead;

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
