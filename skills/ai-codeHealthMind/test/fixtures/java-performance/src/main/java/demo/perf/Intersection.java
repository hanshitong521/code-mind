package demo.perf;

import java.util.ArrayList;
import java.util.List;

public class Intersection {

    public List<String> overlap(List<String> left, List<String> right) {
        List<String> out = new ArrayList<>();
        for (String a : left) {
            for (String b : right) {
                if (left.contains(b)) {
                    out.add(a + b);
                }
            }
        }
        return out;
    }
}
