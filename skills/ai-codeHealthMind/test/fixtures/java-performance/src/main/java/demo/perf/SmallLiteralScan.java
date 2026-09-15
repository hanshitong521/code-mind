package demo.perf;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class SmallLiteralScan {

    public List<String> pick(List<String> values) {
        List<String> allowed = Arrays.asList("new", "open", "closed");
        List<String> out = new ArrayList<>();
        for (String value : values) {
            for (String candidate : values) {
                if (allowed.contains(candidate)) {
                    out.add(value);
                }
            }
        }
        return out;
    }
}
