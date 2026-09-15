package demo.conc;

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
