package demo.dup;

public class NullCheckA {

    public String label(String value) {
        if (value == null) {
            return "unknown";
        }
        return value;
    }
}
