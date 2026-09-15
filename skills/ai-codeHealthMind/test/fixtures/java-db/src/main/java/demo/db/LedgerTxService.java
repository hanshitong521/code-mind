package demo.db;

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
