package demo.clean.cache;

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
