package demo.conc;

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
