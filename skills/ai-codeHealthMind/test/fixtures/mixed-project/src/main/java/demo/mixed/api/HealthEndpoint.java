package demo.mixed.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthEndpoint {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
