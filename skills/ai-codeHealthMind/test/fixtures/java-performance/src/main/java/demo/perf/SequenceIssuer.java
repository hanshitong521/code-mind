package demo.perf;

public class SequenceIssuer {

    public String next(String prefix) {
        long now = System.currentTimeMillis();
        return prefix + "-" + now;
    }
}
