package demo.perf;

import com.alibaba.fastjson.JSON;
import java.util.HashMap;
import java.util.Map;

public class PayloadBroadcaster {

    public Map<String, String> fanOut(Map<String, Object> payload, String[] topics) {
        Map<String, String> out = new HashMap<>();
        String first = JSON.toJSONString(payload);
        out.put(topics[0], first);
        out.put(topics[1], JSON.toJSONString(payload));
        out.put(topics[2], JSON.toJSONString(payload));
        out.put(topics[3], JSON.toJSONString(payload));
        out.put(topics[4], JSON.toJSONString(payload));
        return out;
    }
}
