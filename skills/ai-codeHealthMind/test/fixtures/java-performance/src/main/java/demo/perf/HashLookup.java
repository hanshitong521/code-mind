package demo.perf;

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
