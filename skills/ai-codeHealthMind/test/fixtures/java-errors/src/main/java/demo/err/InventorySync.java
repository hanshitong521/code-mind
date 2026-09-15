package demo.err;

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
